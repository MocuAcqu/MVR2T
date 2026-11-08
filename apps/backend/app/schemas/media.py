"""Phase 04 API 的請求 / 回應 Schema（需與 shared/types/api.ts 保持一致）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str


class MediaInfo(BaseModel):
    media_id: str
    filename: str
    format: str
    kind: Literal["video", "audio"]
    size: int
    duration: float
    container: str
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None
    has_video: bool
    video_codec: str | None
    width: int | None
    height: int | None


class ExtractAudioRequest(BaseModel):
    session_id: str
    media_id: str


class TaskCreated(BaseModel):
    task_id: str


class TaskState(BaseModel):
    task_id: str
    session_id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: float
    stage: str
    detail: str
    message: str | None
    result: Any | None


class FfmpegStatus(BaseModel):
    available: bool
    version: str | None
    source: Literal["settings", "app-runtime", "path", "winget"] | None
    ffmpeg_path: str | None


# ---------------------------------------------------------------------------
# Phase 05：模型與語音辨識
# ---------------------------------------------------------------------------


class ModelInfo(BaseModel):
    id: str
    kind: Literal["asr", "aligner", "llm"]
    display_name: str
    role: str
    repo: str
    revision: str
    license: str
    size_bytes: int
    installed: bool
    downloadable: bool
    available_from_phase: int | None


class ModelsResponse(BaseModel):
    models_dir: str
    models: list[ModelInfo]


class TranscribeRequest(BaseModel):
    session_id: str
    media_id: str
    #: None = 自動偵測；或 Chinese / English / Cantonese / Japanese / Korean
    language: str | None = None


class TranscriptWord(BaseModel):
    text: str
    start: float
    end: float


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    timing: Literal["aligned", "estimated"]
    words: list[TranscriptWord]


class Transcript(BaseModel):
    media_id: str
    language: str | None
    timing: Literal["aligned", "estimated", "mixed"]
    duration: float
    models: dict[str, str | None]
    warnings: list[str]
    segments: list[TranscriptSegment]
