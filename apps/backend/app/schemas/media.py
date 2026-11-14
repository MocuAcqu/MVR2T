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
    #: Phase 10：實際使用的運算裝置（cpu / cuda / metal）與說明（例如「GPU 無法載入，已改用 CPU」）
    device: str | None = None
    device_note: str | None = None


class ExportRequest(BaseModel):
    """POST /api/export（Phase 08）。format = html 是給 Electron 轉成 PDF 的列印版。"""

    session_id: str
    media_id: str
    content: Literal["segments", "segments_audio", "transcript", "summary"]
    format: Literal["txt", "csv", "docx", "html", "srt", "vtt", "json", "md", "zip"]
    # 摘要：前端編輯後的心智圖（樹）與它的 PNG（base64）；沒有就用 AI 產生的原始心智圖
    mindmap: MindMapNode | None = None
    mindmap_png: str | None = Field(default=None, max_length=28_000_000)
    # 只匯出這些摘要類型（含 mindmap）；不給 = 全部
    summary_types: list[SummaryTypeName] | None = None


# --- Phase 09：模型管理 -------------------------------------------------------------------------


class PackageModel(BaseModel):
    id: str
    kind: Literal["asr", "aligner", "llm"]
    display_name: str
    role: str
    repo: str
    revision: str
    license: str
    size_bytes: int
    installed: bool
    #: 已安裝的版本（可能是舊版本）；None = 沒有安裝
    installed_revision: str | None


class PackageRuntime(BaseModel):
    name: str
    version: str
    size_bytes: int
    installed: bool
    supported: bool


class PackageJob(BaseModel):
    action: Literal["download", "verify"]
    status: Literal["queued", "running"]
    stage: str
    current: str
    done_bytes: int
    total_bytes: int
    speed: int
    cancelling: bool


class PackageLast(BaseModel):
    action: Literal["download", "verify"]
    ok: bool
    message: str
    at: float
    problems: list[str]


class ModelPackage(BaseModel):
    id: Literal["asr", "llm", "llm_gpu"]
    name: str
    role: str
    hardware: str
    #: installed / not_installed / partial（下載到一半）/ outdated（有新版本）/ damaged（驗證失敗）/ queued / downloading / verifying
    status: Literal["installed", "not_installed", "partial", "outdated", "damaged", "queued", "downloading", "verifying"]
    size_bytes: int
    missing_bytes: int
    #: 選用（GPU 加速）：不在「全部下載」裡，只在硬體支援時出現
    optional: bool = False
    models: list[PackageModel]
    runtime: PackageRuntime | None
    job: PackageJob | None
    last: PackageLast | None


class UnusedItem(BaseModel):
    key: str
    label: str
    kind: str
    size_bytes: int
    partial: bool


class ModelManagerState(BaseModel):
    models_dir: str
    free_bytes: int
    packages: list[ModelPackage]
    unused: list[UnusedItem]
    busy: bool


# --- Phase 10：硬體偵測與運算裝置 ---------------------------------------------------------------


class GpuInfo(BaseModel):
    vendor: str
    name: str
    vram_total: int | None
    vram_free: int | None
    driver: str | None


class HardwareInfo(BaseModel):
    platform: str
    os_name: str
    arch: str
    cpu_name: str
    cpu_threads: int
    ram_total: int
    ram_available: int
    gpus: list[GpuInfo]
    cuda_available: bool
    cuda_reason: str
    metal_available: bool
    metal_reason: str


class LlmPlanInfo(BaseModel):
    device: Literal["cpu", "cuda", "metal"]
    executable: str | None
    n_gpu_layers: int
    ctx: int
    reason: str
    warnings: list[str]
    cpu_executable: str | None


class AsrPlanInfo(BaseModel):
    device: Literal["cpu", "cuda", "metal"]
    reason: str
    warnings: list[str]


class SystemInfo(BaseModel):
    hardware: HardwareInfo
    #: 摘要（llama.cpp）目前會使用的裝置與原因；記憶體不足時的降級也在 warnings
    llm: LlmPlanInfo
    #: 語音辨識（PyTorch）目前會使用的裝置
    asr: AsrPlanInfo
