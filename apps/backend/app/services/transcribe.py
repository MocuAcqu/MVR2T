"""語音辨識工作（PROJECT_SPEC Phase 05 / §5.4 依序載入 / §9.2 時間偏移）。

輸入：Phase 04 抽取的 audio/manifest.json（每段的檔案與在原始檔中的起點）。
流程（全部在背景執行緒，可隨時取消）：
    1. 載入 Qwen3-ASR → 逐段辨識（文字為簡體，語言自動偵測或指定）→ 卸載並釋放記憶體
    2. 載入 Qwen3-ForcedAligner → 逐段對齊出字／詞時間（只處理支援的語言）→ 卸載
    3. 依標點切句、加上段落起點、去除硬切重疊、中文轉繁體（台灣用語）
    4. 結果存在 Session（記憶體 + 暫存資料夾的 transcript.json，Session 結束即刪除，規格 §8.3）

時間戳記 = 段落在原始檔案中的起點 + 段內時間，所以能直接對回原始影音。
"""
from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from app.core.config import Settings
from app.engines.asr.pipeline import (
    P_ALIGN,
    Cancelled,
    Engines,
    PipelineResult,
    alignment_warnings,
    recognize_and_align,
    segments_to_align,
)
from app.engines.asr.text import CHINESE_LANGUAGES, Sentence, Unit, build_sentences, dedupe_overlaps, shift, to_traditional
from app.engines.asr.worker import EngineSpec, WorkerCancelled, WorkerCrashed, WorkerFailed, run_in_worker
from app.models.registry import QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B
from app.models.store import is_installed
from app.services.media import MediaError
from app.services.model_lock import BUSY_MESSAGE, MODEL_LOCK
from app.services.tasks import Task, TaskCancelled, UserFacingError
from app.session.manager import MediaRecord, Session, SessionManager

# 介面可選的語言（Qwen3-ASR 使用的英文名稱）；None = 自動偵測
LANGUAGE_CHOICES = ("Chinese", "English", "Cantonese", "Japanese", "Korean")


#: engines_factory 的回傳：EngineSpec = 在獨立工作程序執行真實模型（正式路徑）；Engines = 在本程序執行（測試用假模型）
EngineChoice = EngineSpec | Engines


def default_engines(cfg: Settings) -> EngineSpec:
    """真實模型：只傳路徑與設定，模型在工作程序中載入（見 app/engines/asr/worker.py）。"""
    root = cfg.models_root
    aligner_dir = (
        str(QWEN3_FORCED_ALIGNER_0_6B.local_dir(root)) if is_installed(QWEN3_FORCED_ALIGNER_0_6B, root) else None
    )
    return EngineSpec(str(QWEN3_ASR_0_6B.local_dir(root)), aligner_dir, cfg.asr_dtype, cfg.torch_threads, cfg.asr_batch)


def _load_manifest(rec: MediaRecord) -> dict[str, Any]:
    path = rec.dir / "audio" / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise MediaError(409, "請先完成「抽取音訊」，再開始語音辨識。") from e


def run_transcription(task: Task, rec: MediaRecord, engines: EngineChoice, language: str | None) -> dict[str, Any]:
    manifest = _load_manifest(rec)
    audio_dir = rec.dir / "audio"
    total_seconds = sum(s["duration"] for s in manifest["segments"]) or 1.0
    started = time.monotonic()
    # 各步驟耗時（含載入模型），用來評估加速方案（2026-11-10 使用者提議：辨識與對齊同時進行）
    timings: dict[str, float] = {}

    def report(progress: float | None = None, stage: str | None = None, detail: str | None = None) -> None:
        task.update(progress=progress, stage=stage, detail=detail)

    if isinstance(engines, EngineSpec):
        # 正式路徑：兩個步驟各在一個新的工作程序中執行；程序結束時記憶體完全釋放（規格 §5.4）
        def step(phase: str, payload: dict[str, Any]) -> dict[str, Any]:
            try:
                return run_in_worker(phase, engines, payload, report, lambda: task.cancelled, on_start=task.on_cancel)
            except WorkerCancelled as e:
                raise TaskCancelled() from e
            except (WorkerCrashed, WorkerFailed) as e:
                raise UserFacingError(str(e)) from e

        t0 = time.monotonic()
        asr_msg = step("asr", {"manifest": manifest, "audio_dir": str(audio_dir), "language": language})
        timings["asr_seconds"] = round(time.monotonic() - t0, 1)
        raw = asr_msg["raw"]
        warnings = list(asr_msg["warnings"])
        units: dict[int, list[Unit] | None] = {s["index"]: None for s in raw}
        aligner_used = engines.aligner_dir is not None
        if aligner_used and segments_to_align(raw):
            if task.cancelled:
                raise TaskCancelled()
            t0 = time.monotonic()
            al_msg = step("align", {"raw": raw, "audio_dir": str(audio_dir)})
            timings["align_seconds"] = round(time.monotonic() - t0, 1)
            units.update({int(k): ([Unit(**u) for u in v] if v is not None else None) for k, v in al_msg["units"].items()})
            warnings += al_msg["warnings"]
        warnings += alignment_warnings(raw, aligner_used)
        result = PipelineResult(raw=raw, units=units, warnings=warnings)
    else:
        try:
            result = recognize_and_align(manifest, audio_dir, engines, language, report, lambda: task.cancelled)
        except Cancelled as e:
            raise TaskCancelled() from e
        aligner_used = engines.aligner is not None
    if task.cancelled:
        raise TaskCancelled()
    raw, units_by_seg, warnings = result.raw, result.units, result.warnings

    # ---- 3. 組成逐字稿 ----
    task.update(stage="正在整理逐字稿", progress=P_ALIGN, detail="")
    per_segment: list[tuple[float, float, list[Sentence]]] = []
    for s in raw:
        sentences = build_sentences(s["text"], units_by_seg[s["index"]], s["duration"])
        if s["language"] in CHINESE_LANGUAGES:
            for sent in sentences:
                sent.text = to_traditional(sent.text)
                sent.units = [Unit(to_traditional(u.text), u.start, u.end) for u in sent.units]
        per_segment.append((s["start"], s["end"], shift(sentences, s["start"])))
    sentences = dedupe_overlaps(per_segment)

    lang_weight: Counter[str] = Counter()
    for s in raw:
        if s["text"] and s["language"]:
            lang_weight[s["language"]] += s["duration"]
    sentence_timing = {s.timing for s in sentences}  # 不要叫 timings：會蓋掉上面的步驟耗時（2026-11-10 Windows 驗收發現）
    transcript = {
        "media_id": rec.id,
        "language": lang_weight.most_common(1)[0][0] if lang_weight else None,
        "timing": "aligned" if sentence_timing == {"aligned"} else ("estimated" if sentence_timing == {"estimated"} else "mixed"),
        "duration": manifest["duration"],
        "models": {
            "asr": f"{QWEN3_ASR_0_6B.repo}@{QWEN3_ASR_0_6B.revision[:7]}",
            "aligner": f"{QWEN3_FORCED_ALIGNER_0_6B.repo}@{QWEN3_FORCED_ALIGNER_0_6B.revision[:7]}" if aligner_used else None,
        },
        "warnings": warnings,
        "segments": [
            {
                "id": i,
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "timing": s.timing,
                "words": [{"text": u.text, "start": u.start, "end": u.end} for u in s.units],
            }
            for i, s in enumerate(sentences)
        ],
    }
    (rec.dir / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
    rec.transcript = transcript
    elapsed = time.monotonic() - started
    task.update(stage="完成", progress=1.0, detail=f"{len(sentences)} 句")
    return {
        "media_id": rec.id,
        "language": transcript["language"],
        "timing": transcript["timing"],
        "segment_count": len(sentences),
        "warnings": warnings,
        "elapsed_seconds": round(elapsed, 1),
        "audio_seconds": round(total_seconds, 1),
        "timings": timings,
    }


def start_transcription(
    cfg: Settings,
    sessions: SessionManager,
    session: Session,
    media_id: str,
    language: str | None,
    engines_factory: Callable[[Settings], EngineChoice] = default_engines,
) -> Task:
    rec = session.media
    if rec is None or rec.id != media_id:
        raise MediaError(404, "找不到這個媒體，請重新匯入。")
    if language is not None and language not in LANGUAGE_CHOICES:
        raise MediaError(422, f"不支援的語言：{language}")
    busy = [t for t in sessions.tasks.for_session(session.id) if t.status in ("queued", "running")]
    if any(t.kind == "extract-audio" for t in busy):
        raise MediaError(409, "音訊抽取尚未完成。")
    if any(t.kind == "transcribe" for t in busy):
        raise MediaError(409, "語音辨識已在進行中。")
    _load_manifest(rec)  # 尚未抽取音訊 → 409
    if not is_installed(QWEN3_ASR_0_6B, cfg.models_root):
        raise MediaError(
            412,
            "尚未下載語音辨識模型。請在 apps\\backend 執行 .\\.venv\\Scripts\\python.exe -m scripts.download_models 後再試。",
        )
    if not MODEL_LOCK.acquire(blocking=False):
        raise MediaError(409, BUSY_MESSAGE)
    try:
        engines = engines_factory(cfg)
    except Exception:
        MODEL_LOCK.release()
        raise
    rec.transcript = None  # 重新辨識前清除舊結果
    rec.summary = None  # 摘要依附在逐字稿上

    def job(task: Task) -> dict[str, Any]:
        try:
            return run_transcription(task, rec, engines, language)
        except MediaError as e:
            raise UserFacingError(e.message) from e
        finally:
            MODEL_LOCK.release()

    return sessions.tasks.start(session.id, "transcribe", job)
