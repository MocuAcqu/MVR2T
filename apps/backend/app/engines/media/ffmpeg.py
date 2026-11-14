"""FFmpeg / ffprobe 的尋找、探測與指令組裝（PROJECT_SPEC §9 / §11-11）。

安全原則：
- 一律以「參數陣列」呼叫 subprocess，不經過 shell，不把使用者輸入拼成指令字串。
- 傳給 FFmpeg 的檔案路徑都是後端自己產生的 Session 暫存路徑（例如 original.mp4），
  不使用使用者提供的檔名，所以不會被檔名中的特殊字元影響。
- 子行程的 stdin 一律接 DEVNULL：後端自己的 stdin 是 Electron 用來綁定生命週期的管線，
  不能讓 FFmpeg 讀走或繼承。

本檔的解析函式（parse_*、build_*）都是純函式，方便單元測試。
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

EXE_SUFFIX = ".exe" if sys.platform == "win32" else ""

# Windows：不要為 FFmpeg 跳出主控台視窗。
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

FfmpegSource = Literal["settings", "bundled", "app-runtime", "path", "winget"]


# ---------------------------------------------------------------------------
# 1. 尋找 FFmpeg（設定 → 程式資料夾 runtime/ffmpeg → 系統 PATH → winget 安裝位置）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FfmpegLocation:
    ffmpeg: Path
    ffprobe: Path
    source: FfmpegSource


def _pair_in_dir(directory: Path) -> tuple[Path, Path] | None:
    """在資料夾（或其 bin/ 子資料夾）找同時存在的 ffmpeg 與 ffprobe。"""
    for d in (directory, directory / "bin"):
        ff = d / f"ffmpeg{EXE_SUFFIX}"
        fp = d / f"ffprobe{EXE_SUFFIX}"
        if ff.is_file() and fp.is_file():
            return ff, fp
    return None


def _winget_candidates() -> list[Path]:
    """winget 安裝 Gyan.FFmpeg 後，若終端機尚未重開，PATH 還看不到它；直接找安裝位置。"""
    if sys.platform != "win32":
        return []
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    pattern = os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin")
    return [Path(p) for p in sorted(glob.glob(pattern), reverse=True)]


def locate_ffmpeg(settings_dir: str, runtime_dir: Path, bundled_dir: str = "") -> FfmpegLocation | None:
    """依優先順序尋找 FFmpeg；ffmpeg 與 ffprobe 必須來自同一處，避免版本混用。
    順序：設定指定 → 安裝程式內附（Phase 11）→ 程式資料夾 runtime → PATH → winget。"""
    if settings_dir:
        pair = _pair_in_dir(Path(settings_dir))
        if pair:
            return FfmpegLocation(*pair, source="settings")
    if bundled_dir:
        pair = _pair_in_dir(Path(bundled_dir))
        if pair:
            return FfmpegLocation(*pair, source="bundled")
    pair = _pair_in_dir(runtime_dir)
    if pair:
        return FfmpegLocation(*pair, source="app-runtime")
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ff and fp:
        return FfmpegLocation(Path(ff), Path(fp), source="path")
    for d in _winget_candidates():
        pair = _pair_in_dir(d)
        if pair:
            return FfmpegLocation(*pair, source="winget")
    return None


def run_quiet(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """執行短時間的 FFmpeg / ffprobe 指令並收集輸出。"""
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def parse_version(output: str) -> str | None:
    """`ffmpeg -version` 第一行：ffmpeg version 7.1-full_build-www.gyan.dev Copyright ..."""
    m = re.match(r"\s*ffmpeg version (\S+)", output)
    return m.group(1) if m else None


def ffmpeg_version(loc: FfmpegLocation) -> str | None:
    try:
        r = run_quiet([str(loc.ffmpeg), "-hide_banner", "-version"], timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_version(r.stdout) if r.returncode == 0 else None


# ---------------------------------------------------------------------------
# 2. ffprobe：檢查檔案能否解碼、取得長度與音訊資訊
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    duration: float  # 秒
    format_name: str
    has_audio: bool
    has_video: bool
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    video_codec: str | None = None
    width: int | None = None
    height: int | None = None
    warnings: list[str] = field(default_factory=list)


class ProbeError(Exception):
    """檔案無法被辨識為可處理的影音（損壞、格式不符、沒有音訊）。訊息給使用者看。"""


def build_probe_args(ffprobe: Path, media: Path) -> list[str]:
    return [
        str(ffprobe),
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(media),
    ]


def _to_float(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f >= 0 and f == f else None  # 排除負數與 NaN


def _to_int(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# 「看似」可以處理、實際上只是附件或封面圖的影像串流
_ATTACHED_PIC = "attached_pic"


def parse_probe(stdout: str) -> ProbeResult:
    """把 ffprobe JSON 轉成 ProbeResult；資訊不足時丟出 ProbeError。"""
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError as e:
        raise ProbeError("無法讀取這個檔案的影音資訊，檔案可能已損壞。") from e
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get(_ATTACHED_PIC)),
        None,
    )
    if not streams or not fmt:
        raise ProbeError("無法辨識這個檔案的影音格式，檔案可能已損壞。")
    if audio is None:
        raise ProbeError("這個檔案沒有音訊軌，無法進行語音辨識。")

    duration = _to_float(fmt.get("duration")) or _to_float(audio.get("duration"))
    if not duration:
        raise ProbeError("無法取得這個檔案的長度，檔案可能已損壞或不完整。")

    return ProbeResult(
        duration=duration,
        format_name=str(fmt.get("format_name") or ""),
        has_audio=True,
        has_video=video is not None,
        audio_codec=audio.get("codec_name"),
        sample_rate=_to_int(audio.get("sample_rate")),
        channels=_to_int(audio.get("channels")),
        video_codec=video.get("codec_name") if video else None,
        width=_to_int(video.get("width")) if video else None,
        height=_to_int(video.get("height")) if video else None,
    )


def probe(loc: FfmpegLocation, media: Path, timeout: float = 60) -> ProbeResult:
    try:
        r = run_quiet(build_probe_args(loc.ffprobe, media), timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ProbeError("讀取影音資訊逾時，檔案可能已損壞。") from e
    if r.returncode != 0:
        raise ProbeError("無法讀取這個檔案，檔案可能已損壞或不是有效的影音檔。")
    return parse_probe(r.stdout)


# ---------------------------------------------------------------------------
# 3. 抽取音訊：16 kHz、單聲道、PCM WAV（規格 §9.1），同時偵測靜音位置供切段使用
# ---------------------------------------------------------------------------

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1

# 靜音偵測參數：-35 dB 以下持續 0.3 秒視為靜音（句子間的停頓）。
SILENCE_NOISE_DB = -35
SILENCE_MIN_SECONDS = 0.3


def build_extract_args(ffmpeg: Path, src: Path, dst: Path) -> list[str]:
    """
    -nostdin            不讀 stdin（避免干擾後端的生命週期管線）
    -vn -sn -dn         只要音訊
    -map 0:a:0          取第一條音訊軌
    silencedetect       在同一次解碼中找出靜音區段，結果寫在 stderr
    -progress pipe:1    以 key=value 形式把進度寫到 stdout
    """
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i", str(src),
        "-map", "0:a:0",
        "-vn", "-sn", "-dn",
        "-ac", str(TARGET_CHANNELS),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_SECONDS}",
        "-progress", "pipe:1",
        "-nostats",
        "-loglevel", "info",
        str(dst),
    ]


def parse_progress_seconds(line: str) -> float | None:
    """解析 `-progress` 輸出的 out_time_us / out_time_ms（兩者單位其實都是微秒）。"""
    m = re.match(r"out_time_(?:us|ms)=(\d+)", line.strip())
    return int(m.group(1)) / 1_000_000 if m else None


_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def parse_silences(stderr_lines: list[str], total_duration: float) -> list[tuple[float, float]]:
    """從 silencedetect 的輸出組出 [(start, end), ...]；檔尾未結束的靜音以總長度收尾。"""
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for line in stderr_lines:
        if (m := _SILENCE_START.search(line)) is not None:
            start = max(0.0, float(m.group(1)))
        elif (m := _SILENCE_END.search(line)) is not None and start is not None:
            end = min(total_duration, float(m.group(1)))
            if end > start:
                silences.append((start, end))
            start = None
    if start is not None and total_duration > start:
        silences.append((start, total_duration))
    return silences
