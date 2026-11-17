"""YouTube 連結：讀取影片資訊、只下載音訊、（可選）使用影片作者提供的字幕（使用者決定 2026-11-15）。

- 用 yt-dlp（app/models/ytdlp.py 安裝的官方執行檔）。只有這一步需要連網，之後的辨識與摘要都在本機。
- 只接受單一 YouTube 影片：網址先在後端轉成標準的 https://www.youtube.com/watch?v=<11 碼 ID>，
  不把使用者輸入的任意網址交給 yt-dlp（也去掉播放清單參數）。不支援登入／cookies、會員限定、私人、直播。
- YouTube 需要 JavaScript 執行環境：Electron 以 MVR2T_JS_RUNTIME 傳入自己的執行檔，
  加上 ELECTRON_RUN_AS_NODE=1 當作 Node.js 使用（Electron 44 內建 Node 24，yt-dlp 需要 22 以上）。
- 下載的音訊放在 Session 暫存（original.<ext>），之後與本機匯入的檔案走相同流程（抽取音訊 → 辨識 → 摘要）。
- 字幕：只用作者上傳的字幕（不用 YouTube 自動產生的字幕），轉成與語音辨識相同格式的逐字稿（source = subtitles）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.engines.asr.text import CHINESE_LANGUAGES, to_traditional
from app.engines.media import ffmpeg as ff
from app.models.ytdlp import YtDlpComponent
from app.services.media import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, MediaError, _check_free_space, media_info, require_ffmpeg
from app.services.tasks import Task, TaskCancelled, UserFacingError
from app.session.manager import MediaRecord, Session, SessionManager, safe_rmtree

YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"})
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
PROGRESS_PREFIX = "MVR2T-PROGRESS"
#: 下載佔進度條 95%，其餘是檢查檔案與整理字幕
DOWNLOAD_SHARE = 0.95
PROBE_TIMEOUT = 120.0
#: 估計不到大小時，以 128 kbps 估計音訊大小（檢查磁碟空間用）
FALLBACK_BYTES_PER_SECOND = 16_000


def parse_video_id(text: str) -> str | None:
    """與 apps/desktop/src/lib/youtube.ts 相同的規則（後端再檢查一次，不信任前端）。"""
    text = (text or "").strip()
    if not text:
        return None
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    try:
        u = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        vid = u.path.split("/")[1] if len(u.path.split("/")) > 1 else None
    elif u.path == "/watch":
        vid = (urllib.parse.parse_qs(u.query).get("v") or [None])[0]
    else:
        m = re.match(r"^/(?:shorts|embed|live)/([^/?#]+)", u.path)
        vid = m.group(1) if m else None
    return vid if vid and VIDEO_ID.match(vid) else None


def canonical_url(text: str) -> tuple[str, str]:
    vid = parse_video_id(text)
    if vid is None:
        raise MediaError(422, "這不是有效的 YouTube 影片網址。")
    return vid, f"https://www.youtube.com/watch?v={vid}"


# ---------------------------------------------------------------------------
# 執行 yt-dlp
# ---------------------------------------------------------------------------


def ytdlp_argv(exe: Path) -> list[str]:
    """yt-dlp 的命令列開頭（測試以假的 Python 腳本取代）。"""
    return [str(exe)]


def require_component(comp: YtDlpComponent) -> Path:
    exe = comp.executable()
    if exe is None:
        raise MediaError(412, "尚未下載 YouTube 下載元件。請到「模型管理」下載「YouTube 下載元件」。")
    return exe


def base_args(cfg: Settings, comp: YtDlpComponent, loc: ff.FfmpegLocation | None) -> tuple[list[str], dict[str, str]]:
    exe = require_component(comp)
    args = [
        *ytdlp_argv(exe),
        "--ignore-config",
        "--no-playlist",
        "--no-color",
        "--cache-dir", str(comp.dir / "cache"),
    ]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if cfg.js_runtime:
        args += ["--js-runtimes", f"node:{cfg.js_runtime}"]
        env["ELECTRON_RUN_AS_NODE"] = "1"  # Electron 執行檔當作 Node.js 使用（對真的 Node.js 沒有影響）
    else:
        args += ["--js-runtimes", "node"]  # 開發者直接啟動後端時：使用 PATH 上的 Node.js（Deno 預設已啟用）
    if loc is not None:
        args += ["--ffmpeg-location", str(loc.ffmpeg.parent)]
    return args, env


ERRORS: tuple[tuple[str, str], ...] = (
    ("private video", "這是私人影片，無法下載。"),
    ("members-only", "這是會員限定影片，無法下載。"),
    ("join this channel", "這是會員限定影片，無法下載。"),
    ("confirm your age", "這部影片有年齡限制，需要登入 YouTube，本程式不支援。"),
    ("not a bot", "YouTube 要求驗證（「確認您不是機器人」）。請稍後再試，或先到「模型管理」更新 YouTube 下載元件。"),
    ("live event will begin", "直播尚未開始，無法下載。"),
    ("is live", "不支援正在進行的直播，請等直播結束後再試。"),
    ("premieres in", "首播尚未開始，無法下載。"),
    ("video unavailable", "影片無法觀看（可能已刪除、設為私人，或在這個地區無法觀看）。"),
    ("not available in your country", "這部影片在你所在的地區無法觀看。"),
    ("copyright", "影片因著作權問題無法觀看。"),
    ("unable to download webpage", "無法連線到 YouTube，請檢查網路後再試。"),
    ("getaddrinfo failed", "無法連線到 YouTube，請檢查網路後再試。"),
    ("name or service not known", "無法連線到 YouTube，請檢查網路後再試。"),
    ("timed out", "連線到 YouTube 逾時，請檢查網路後再試。"),
    ("javascript runtime", "YouTube 下載元件找不到 JavaScript 執行環境，請重新啟動程式後再試。"),
    ("n challenge", "YouTube 改版，目前的下載元件無法處理。請到「模型管理」更新 YouTube 下載元件。"),
    ("signature", "YouTube 改版，目前的下載元件無法處理。請到「模型管理」更新 YouTube 下載元件。"),
    ("requested format is not available", "找不到可下載的音訊格式。請到「模型管理」更新 YouTube 下載元件後再試。"),
)


def friendly_error(stderr: str) -> str:
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith("ERROR:")] or lines[-3:]
    text = " ".join(errors).lower()
    for needle, msg in ERRORS:
        if needle in text:
            return msg
    last = errors[-1] if errors else "（沒有錯誤訊息）"
    return f"YouTube 下載失敗：{last[:300]}。如果一直失敗，請到「模型管理」更新 YouTube 下載元件。"


def _kill_tree(proc: subprocess.Popen[Any]) -> None:
    """yt-dlp 的官方執行檔是 PyInstaller 單一檔案：實際工作在子行程，要連同子行程一起結束。"""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=ff.CREATE_NO_WINDOW, check=False,
        )
    else:
        try:
            os.killpg(proc.pid, 9)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()


def _popen(args: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=ff.CREATE_NO_WINDOW,
        start_new_session=sys.platform != "win32",
    )


# ---------------------------------------------------------------------------
# 讀取影片資訊
# ---------------------------------------------------------------------------


def _audio_size(info: dict[str, Any]) -> int | None:
    audio = [f for f in info.get("formats") or [] if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    audio.sort(key=lambda f: (f.get("ext") == "m4a", f.get("abr") or 0), reverse=True)
    for f in audio:
        size = f.get("filesize") or f.get("filesize_approx")
        if size:
            return int(size)
    return None


def subtitle_choices(info: dict[str, Any]) -> list[dict[str, str]]:
    """作者上傳的字幕（不含自動產生的字幕與聊天室）。"""
    out = []
    for lang, tracks in sorted((info.get("subtitles") or {}).items()):
        if lang == "live_chat" or not tracks:
            continue
        name = next((t.get("name") for t in tracks if t.get("name")), None) or lang
        out.append({"lang": lang, "name": str(name)})
    return out


def video_summary(info: dict[str, Any], url: str) -> dict[str, Any]:
    live = info.get("live_status")
    if info.get("is_live") or live in ("is_live", "is_upcoming", "post_live"):
        raise MediaError(422, "不支援直播（或尚未結束的直播），請等直播結束並處理完成後再試。")
    if info.get("_type") == "playlist":
        raise MediaError(422, "只支援單一影片，不支援播放清單。")
    duration = info.get("duration")
    return {
        "video_id": str(info.get("id") or ""),
        "url": url,
        "title": str(info.get("title") or "YouTube 影片"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": float(duration) if duration else None,
        "audio_size": _audio_size(info),
        "subtitles": subtitle_choices(info),
    }


def probe_video(cfg: Settings, comp: YtDlpComponent, url_text: str) -> dict[str, Any]:
    """讀取影片資訊（不下載）。在 API 的執行緒中執行，最多約 2 分鐘。"""
    _, url = canonical_url(url_text)
    args, env = base_args(cfg, comp, None)
    proc = _popen([*args, "--dump-single-json", "--skip-download", url], env)
    try:
        out, err = proc.communicate(timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise MediaError(504, "讀取影片資訊逾時，請檢查網路後再試。") from None
    if proc.returncode != 0:
        raise MediaError(502, friendly_error(err))
    try:
        info = json.loads(out)
    except ValueError:
        raise MediaError(502, friendly_error(err or "無法讀取影片資訊")) from None
    return video_summary(info, url)


# ---------------------------------------------------------------------------
# 字幕（WebVTT）→ 逐字稿
# ---------------------------------------------------------------------------

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_TAG = re.compile(r"<[^>]+>")


def _ts(text: str) -> float:
    m = _TS.fullmatch(text.strip())
    if not m:
        raise ValueError(text)
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text: str) -> list[dict[str, Any]]:
    """WebVTT → [{start, end, text}]；去掉樣式標籤、合併同一則字幕的多行、去除與上一則完全相同的重複。"""
    cues: list[dict[str, Any]] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("﻿", ""))
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines()]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        left, right = lines[idx].split("-->", 1)
        try:
            start, end = _ts(left), _ts(right.strip().split()[0])
        except (ValueError, IndexError):
            continue
        body = " ".join(_TAG.sub("", ln) for ln in lines[idx + 1 :] if ln)
        body = re.sub(r"\s+", " ", body.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")).strip()
        if not body or end <= start:
            continue
        if cues and cues[-1]["text"] == body and start - cues[-1]["end"] < 0.05:
            cues[-1]["end"] = end
            continue
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": body})
    return cues


LANGUAGE_NAMES = {"zh": "Chinese", "yue": "Cantonese", "en": "English", "ja": "Japanese", "ko": "Korean"}


def language_name(lang: str) -> str:
    """YouTube 的語言代碼（zh-Hant、en-US…）→ 逐字稿使用的名稱（與語音辨識一致：Chinese、English…）。"""
    low = lang.lower()
    if low in ("zh-hk", "zh-yue") or low.startswith("yue"):
        return "Cantonese"
    return LANGUAGE_NAMES.get(low.split("-", 1)[0], lang)


def subtitle_transcript(media_id: str, lang: str, name: str, cues: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    code = language_name(lang)
    chinese = code in CHINESE_LANGUAGES
    return {
        "media_id": media_id,
        "source": "subtitles",
        "language": code,
        "timing": "aligned",
        "duration": duration,
        "models": {"asr": None, "aligner": None, "subtitles": f"YouTube {lang}"},
        "warnings": [f"這份逐字稿來自影片作者提供的字幕（{name}），沒有經過語音辨識。"],
        "segments": [
            {
                "id": i,
                "start": c["start"],
                "end": c["end"],
                "text": to_traditional(c["text"]) if chinese else c["text"],
                "timing": "aligned",
                "words": [],
            }
            for i, c in enumerate(cues)
        ],
    }


# ---------------------------------------------------------------------------
# 下載（背景工作）
# ---------------------------------------------------------------------------


def _safe_title(title: str) -> str:
    t = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', " ", title).strip().strip(".")
    return (t or "YouTube 影片")[:150]


def run_download(
    task: Task,
    cfg: Settings,
    comp: YtDlpComponent,
    loc: ff.FfmpegLocation,
    session: Session,
    root: Path,
    url: str,
    title: str,
    subtitle: dict[str, str] | None,
) -> dict[str, Any]:
    rec_id = uuid.uuid4().hex
    media_dir = session.dir / "media" / rec_id
    media_dir.mkdir(parents=True)
    ok = False
    try:
        args, env = base_args(cfg, comp, loc)
        args += [
            "--format", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
            "--output", str(media_dir / "original.%(ext)s"),
            "--no-mtime",
            "--no-part",
            "--newline",
            "--progress-template",
            f"download:{PROGRESS_PREFIX} %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s",
        ]
        if subtitle:
            args += ["--write-subs", "--sub-langs", subtitle["lang"], "--sub-format", "vtt"]
        task.update(stage="正在連線到 YouTube", progress=0.0, detail="")
        proc = _popen([*args, url], env)
        task.on_cancel(lambda: _kill_tree(proc))
        err_lines: list[str] = []

        def drain() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                err_lines.append(line.rstrip())

        t = threading.Thread(target=drain, daemon=True)
        t.start()
        assert proc.stdout is not None
        for line in proc.stdout:
            if task.cancelled:
                break
            if line.startswith(PROGRESS_PREFIX):
                parts = line.split()[1:]
                nums = [float(p) if p not in ("NA", "None") else 0.0 for p in parts] + [0.0, 0.0, 0.0]
                done, total = nums[0], nums[1] or nums[2]
                if total > 0:
                    task.update(
                        stage="正在下載音訊",
                        progress=DOWNLOAD_SHARE * min(1.0, done / total),
                        detail=f"{done / 1024**2:,.1f} / {total / 1024**2:,.1f} MB",
                    )
            elif "[info]" in line and "subtitles" in line.lower():
                task.update(stage="正在下載字幕")
        proc.wait()
        t.join(timeout=5)
        if task.cancelled:
            raise TaskCancelled()
        if proc.returncode != 0:
            raise UserFacingError(friendly_error("\n".join(err_lines)))

        files = [p for p in media_dir.glob("original.*") if p.suffix.lower() not in (".vtt", ".part", ".ytdl", ".json")]
        if len(files) != 1:
            raise UserFacingError("下載的檔案不完整，請再試一次。")
        audio = files[0]
        ext = audio.suffix.lstrip(".").lower()
        if ext not in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
            raise UserFacingError(f"下載到不支援的音訊格式（{ext}）。請到「模型管理」更新 YouTube 下載元件後再試。")

        task.update(stage="正在檢查檔案", progress=DOWNLOAD_SHARE, detail="")
        try:
            probed = ff.probe(loc, audio)
        except ff.ProbeError as e:
            raise UserFacingError(str(e)) from e
        size = audio.stat().st_size
        display = f"{_safe_title(title)}.{ext}"
        info = {**media_info(rec_id, display, ext, "audio", size, probed), "origin": "youtube", "source_url": url}
        rec = MediaRecord(rec_id, display, ext, "audio", size, audio, info)

        used_subtitles = False
        warnings: list[str] = []
        if subtitle:
            vtt = next(iter(sorted(media_dir.glob("original*.vtt"))), None)
            cues = parse_vtt(vtt.read_text(encoding="utf-8", errors="replace")) if vtt else []
            if cues:
                rec.transcript = subtitle_transcript(rec_id, subtitle["lang"], subtitle.get("name") or subtitle["lang"], cues, round(probed.duration, 3))
                (media_dir / "transcript.json").write_text(json.dumps(rec.transcript, ensure_ascii=False), encoding="utf-8")
                used_subtitles = True
            else:
                warnings.append("沒有取得影片字幕，請改用語音辨識。")
        session.media = rec
        ok = True
        task.update(stage="完成", progress=1.0, detail="")
        return {"media": info, "subtitles": used_subtitles, "warnings": warnings}
    finally:
        if not ok:
            safe_rmtree(media_dir, root)


def start_download(
    cfg: Settings,
    sessions: SessionManager,
    session: Session,
    comp: YtDlpComponent,
    url_text: str,
    title: str,
    subtitle: dict[str, str] | None,
    duration: float | None,
    audio_size: int | None,
) -> Task:
    _, url = canonical_url(url_text)
    require_component(comp)
    loc = require_ffmpeg(cfg)
    if subtitle is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", subtitle.get("lang", "")):
        raise MediaError(422, "字幕語言不正確。")
    # 一個 Session 只處理一個媒體：先清掉舊的（會取消這個 Session 的所有工作，所以要在建立新工作之前）
    sessions.clear_media(session)
    _check_free_space(session.dir, audio_size or int((duration or 3600) * FALLBACK_BYTES_PER_SECOND))
    return sessions.tasks.start(
        session.id, "youtube", lambda task: run_download(task, cfg, comp, loc, session, sessions.root, url, title, subtitle)
    )


def youtube_busy(sessions: SessionManager) -> Callable[[], bool]:
    """刪除元件前檢查：有沒有正在下載的 YouTube 工作。"""

    def busy() -> bool:
        return any(t.kind == "youtube" and t.status in ("queued", "running") for t in sessions.tasks.all_tasks())

    return busy
