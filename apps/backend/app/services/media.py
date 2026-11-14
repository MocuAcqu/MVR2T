"""媒體匯入與音訊抽取（PROJECT_SPEC Phase 04 / §2.1-A / §9）。

流程：
1. 匯入：Renderer 以串流方式上傳檔案內容，後端寫入 Session 暫存（= 複製一份，規格 §8.3「原始媒體副本」）。
   後端重新驗證副檔名與大小（不信任前端），再用 ffprobe 確認能解碼、有音訊，並取得長度。
2. 抽取：背景工作執行 FFmpeg → 16 kHz 單聲道 WAV，同時偵測靜音；接著依靜音切段。
   進度 = FFmpeg 已處理秒數 / 總長度（佔 90%）+ 切段（佔 10%）。可隨時取消。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import uuid
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anyio

from app.core.config import Settings
from app.engines.media import ffmpeg as ff
from app.engines.media.segmenter import Cancelled, SegmentParams, plan_segments, write_segments
from app.services.tasks import Task, TaskCancelled, UserFacingError
from app.session.manager import MediaRecord, Session, SessionManager, safe_rmtree

VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "mkv", "webm"})
AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "flac", "aac", "ogg"})

# 磁碟空間保留量：除了檔案本身，另外保留 500 MB 給系統與其他程式。
DISK_MARGIN_BYTES = 500 * 1024**2
# 16 kHz、單聲道、16-bit = 每秒 32,000 bytes；抽出的 WAV + 切段約為 2 倍。
WAV_BYTES_PER_SECOND = 32_000


class MediaError(Exception):
    """匯入階段的錯誤；status 對應 HTTP 狀態碼，訊息給使用者看。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def media_kind(filename: str) -> tuple[str, str] | None:
    """回傳 (副檔名, video|audio)；不支援時回傳 None。需與 shared/constants/media.ts 一致。"""
    if "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return ext, "video"
    if ext in AUDIO_EXTENSIONS:
        return ext, "audio"
    return None


def require_ffmpeg(cfg: Settings) -> ff.FfmpegLocation:
    loc = ff.locate_ffmpeg(cfg.ffmpeg_dir, cfg.runtime_ffmpeg_dir, cfg.bundled_ffmpeg_dir)
    if loc is None:
        raise MediaError(503, "找不到 FFmpeg。請先安裝 FFmpeg（Windows：winget install Gyan.FFmpeg），然後重新啟動程式。")
    return loc


def _check_free_space(path: Path, needed: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < needed + DISK_MARGIN_BYTES:
        need_gb = (needed + DISK_MARGIN_BYTES) / 1024**3
        raise MediaError(507, f"磁碟空間不足：處理這個檔案約需 {need_gb:.1f} GB 可用空間。")


def media_info(rec_id: str, display_name: str, ext: str, kind: str, size: int, p: ff.ProbeResult) -> dict[str, Any]:
    return {
        "media_id": rec_id,
        "filename": display_name,
        "format": ext,
        "kind": kind,
        "size": size,
        "duration": round(p.duration, 3),
        "container": p.format_name,
        "audio_codec": p.audio_codec,
        "sample_rate": p.sample_rate,
        "channels": p.channels,
        "has_video": p.has_video,
        "video_codec": p.video_codec,
        "width": p.width,
        "height": p.height,
    }


async def import_media(
    cfg: Settings,
    sessions: SessionManager,
    session: Session,
    filename: str,
    content_length: int | None,
    chunks: AsyncIterator[bytes],
) -> MediaRecord:
    # 1. 驗證（規格 §11-9：後端重新驗證格式與大小）
    display_name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()[:255] or "media"
    kind = media_kind(display_name)
    if kind is None:
        raise MediaError(415, "不支援這個檔案格式。")
    ext, kind_name = kind
    if content_length is None:
        raise MediaError(411, "缺少檔案大小資訊。")
    if content_length <= 0:
        raise MediaError(400, "檔案是空的。")
    if content_length > cfg.max_upload_bytes:
        raise MediaError(413, f"檔案太大：上限為 {cfg.max_upload_bytes / 1024**3:.0f} GB。")
    loc = require_ffmpeg(cfg)

    # 2. 一個 Session 只處理一個媒體：換檔時先清掉舊的（可能要等 FFmpeg 結束，放到執行緒避免卡住伺服器）
    await anyio.to_thread.run_sync(sessions.clear_media, session)
    _check_free_space(session.dir, content_length)

    # 3. 串流寫入暫存（檔名由後端決定，不使用使用者的檔名）
    rec_id = uuid.uuid4().hex
    media_dir = session.dir / "media" / rec_id
    media_dir.mkdir(parents=True)
    dst = media_dir / f"original.{ext}"
    written = 0
    ok = False
    try:
        with dst.open("wb") as f:
            async for chunk in chunks:
                written += len(chunk)
                if written > content_length or written > cfg.max_upload_bytes:
                    raise MediaError(413, "實際上傳的資料比宣告的檔案大小還多。")
                f.write(chunk)
        if written != content_length:
            raise MediaError(400, "檔案沒有完整上傳，請重新匯入。")

        # 4. ffprobe：能否解碼、有沒有音訊、長度
        try:
            probed = await anyio.to_thread.run_sync(ff.probe, loc, dst)
        except ff.ProbeError as e:
            raise MediaError(422, str(e)) from e
        info = media_info(rec_id, display_name, ext, kind_name, written, probed)
        rec = MediaRecord(rec_id, display_name, ext, kind_name, written, dst, info)
        session.media = rec
        ok = True
        return rec
    finally:
        if not ok:  # 包含使用者取消上傳（連線中斷）的情況
            safe_rmtree(media_dir, sessions.root)


# ---------------------------------------------------------------------------
# 抽取音訊 + 切段（背景工作）
# ---------------------------------------------------------------------------

EXTRACT_SHARE = 0.9  # 進度條中「抽取」所佔比例，其餘為切段


def _wav_duration(path: Path) -> tuple[float, int, int]:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate(), w.getframerate(), w.getnchannels()


def run_extraction(
    task: Task,
    loc: ff.FfmpegLocation,
    rec: MediaRecord,
    root: Path,
    params: SegmentParams = SegmentParams(),
) -> dict[str, Any]:
    out_dir = rec.dir / "audio"
    safe_rmtree(out_dir, root)
    out_dir.mkdir(parents=True)
    wav = out_dir / "audio.wav"
    total = float(rec.info["duration"]) or 1.0

    try:
        # ---- 1. FFmpeg 抽取 ----
        task.update(stage="正在抽取音訊", progress=0.0)
        proc = subprocess.Popen(
            ff.build_extract_args(loc.ffmpeg, rec.path, wav),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=ff.CREATE_NO_WINDOW,
        )
        task.on_cancel(proc.kill)  # 取消 → 立即終止 FFmpeg

        stderr_lines: list[str] = []

        def drain_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_lines.append(line.rstrip())

        t_err = threading.Thread(target=drain_stderr, daemon=True)
        t_err.start()
        assert proc.stdout is not None
        for line in proc.stdout:
            sec = ff.parse_progress_seconds(line)
            if sec is not None:
                task.update(progress=EXTRACT_SHARE * min(1.0, sec / total), detail=f"{min(sec, total):.0f} / {total:.0f} 秒")
        rc = proc.wait()
        t_err.join(timeout=5)

        if task.cancelled:
            raise TaskCancelled()
        if rc != 0 or not wav.exists():
            tail = " / ".join(line for line in stderr_lines[-3:] if line)
            raise UserFacingError(f"FFmpeg 無法抽取音訊（代碼 {rc}）。{tail}")

        # ---- 2. 切段 ----
        duration, rate, channels = _wav_duration(wav)
        silences = ff.parse_silences(stderr_lines, duration)
        plans = plan_segments(duration, silences, params)
        task.update(stage="正在切段", progress=EXTRACT_SHARE, detail=f"0 / {len(plans)} 段")

        def on_seg(done: int, n: int) -> None:
            task.update(progress=EXTRACT_SHARE + (1 - EXTRACT_SHARE) * done / n, detail=f"{done} / {n} 段")

        try:
            write_segments(wav, plans, out_dir / "segments", on_progress=on_seg, is_cancelled=lambda: task.cancelled)
        except Cancelled as e:
            raise TaskCancelled() from e

        result = {
            "media_id": rec.id,
            "sample_rate": rate,
            "channels": channels,
            "duration": round(duration, 3),
            "silence_count": len(silences),
            "params": {
                "target_seconds": params.target_seconds,
                "window_seconds": params.window_seconds,
                "min_seconds": params.min_seconds,
                "overlap_seconds": params.overlap_seconds,
            },
            "segments": [
                {"index": p.index, "start": p.start, "end": p.end, "duration": round(p.duration, 3), "boundary": p.boundary}
                for p in plans
            ],
        }
        # 給 Phase 05（ASR）讀取的清單：檔案位置 + 每段在原始時間軸的起點。
        manifest = {**result, "files": [f"segments/seg_{p.index:04d}.wav" for p in plans]}
        (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        rec.audio = result
        task.update(stage="完成", progress=1.0, detail=f"{len(plans)} 段")
        return result
    except BaseException:
        safe_rmtree(out_dir, root)  # 失敗或取消：不留下半成品
        raise


def start_extraction(cfg: Settings, sessions: SessionManager, session: Session, media_id: str) -> Task:
    rec = session.media
    if rec is None or rec.id != media_id:
        raise MediaError(404, "找不到這個媒體，請重新匯入。")
    busy = [t for t in sessions.tasks.for_session(session.id) if t.status in ("queued", "running")]
    if any(t.kind == "extract-audio" for t in busy):
        raise MediaError(409, "音訊抽取已在進行中。")
    if any(t.kind == "transcribe" for t in busy):
        raise MediaError(409, "語音辨識進行中，請等它完成或取消後再重新抽取。")
    if any(t.kind == "summarize" for t in busy):
        raise MediaError(409, "摘要產生中，請等它完成或取消後再重新抽取。")
    rec.transcript = None  # 音訊重新抽取後，舊的逐字稿時間就不再對應
    rec.summary = None
    loc = require_ffmpeg(cfg)
    _check_free_space(session.dir, int(float(rec.info["duration"]) * WAV_BYTES_PER_SECOND * 2.2))
    return sessions.tasks.start(session.id, "extract-audio", lambda task: run_extraction(task, loc, rec, sessions.root))
