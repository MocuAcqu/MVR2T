"""Phase 04 API 的請求 / 回應 Schema（需與 shared/types/api.ts 保持一致）。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class RuntimeInfo(BaseModel):
    name: str  # llama.cpp
    version: str  # release tag（空字串 = 尚未固定）
    installed: bool


class ModelsResponse(BaseModel):
    models_dir: str
    models: list[ModelInfo]
    runtimes: list[RuntimeInfo]


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


# --- Phase 06：摘要 -------------------------------------------------------------

SummaryTypeName = Literal["overview", "key_points", "notes", "topics", "keywords", "action_items", "qa", "mindmap"]


class SummaryRequest(BaseModel):
    session_id: str
    media_id: str
    #: 要產生的內容（至少一種）
    types: list[str]


class TimeSpan(BaseModel):
    start: float
    end: float


class SummaryPoint(BaseModel):
    text: str
    refs: list[int]
    time: TimeSpan | None


class SummarySection(BaseModel):
    title: str
    bullets: list[str]
    refs: list[int]
    time: TimeSpan | None


class SummaryTopic(BaseModel):
    title: str
    description: str
    refs: list[int]
    time: TimeSpan | None


class SummaryAction(BaseModel):
    task: str
    owner: str
    due: str
    refs: list[int]
    time: TimeSpan | None


class SummaryQa(BaseModel):
    question: str
    conclusion: str
    refs: list[int]
    time: TimeSpan | None


class MindMapNode(BaseModel):
    id: str
    text: str
    kind: Literal["central", "main", "sub", "detail", "conclusion"]
    refs: list[int]
    time: TimeSpan | None
    children: list[MindMapNode]


class MindMapRequest(BaseModel):
    session_id: str
    media_id: str


class SummaryResults(BaseModel):
    overview: str | None = None
    key_points: list[SummaryPoint] | None = None
    notes: list[SummarySection] | None = None
    topics: list[SummaryTopic] | None = None
    keywords: list[str] | None = None
    action_items: list[SummaryAction] | None = None
    qa: list[SummaryQa] | None = None
    mindmap: MindMapNode | None = None


class Summary(BaseModel):
    media_id: str
    types: list[SummaryTypeName]
    results: SummaryResults
    model: str
    chunks: int
    levels: int
    elapsed_seconds: float


class ExportRequest(BaseModel):
    """POST /api/export（Phase 08）。format = html 是給 Electron 轉成 PDF 的列印版。"""

    session_id: str
    media_id: str
    content: Literal["segments", "segments_audio", "transcript", "summary"]
    format: Literal["txt", "csv", "docx", "html", "srt", "vtt", "json", "md", "zip"]
    # 摘要：前端編輯後的心智圖（樹）與它的 PNG（base64）；沒有就用 AI 產生的原始心智圖
    mindmap: MindMapNode | None = None
    mindmap_png: str | None = Field(default=None, max_length=28_000_000)
