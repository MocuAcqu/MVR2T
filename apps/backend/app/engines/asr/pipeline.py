"""辨識 + 對齊的核心流程（不依賴 FastAPI，可在背景工作程序中執行）。

recognize_and_align() 依序：載入 ASR → 逐段辨識 → 卸載 → 載入對齊模型 → 逐段對齊 → 卸載。
進度、取消與模型都由呼叫端注入，所以同一份流程可以：
- 在獨立的工作程序中搭配真實模型執行（正式路徑，見 worker.py），
- 在測試中搭配假模型直接執行。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.engines.asr.text import Unit
from app.models.registry import ALIGNER_LANGUAGES

# 日文、韓文的對齊需要額外的斷詞套件（nagisa / soynlp），第一版未安裝 → 退回估計時間
_ALIGNER_EXTRA_DEPS = {"Japanese": "nagisa", "Korean": "soynlp"}

# 進度比例（整體 0 ~ 1）
P_LOAD_ASR, P_ASR, P_LOAD_ALIGN, P_ALIGN = 0.04, 0.70, 0.73, 0.97


class Cancelled(Exception):
    pass


class AsrBackend(Protocol):
    def load(self) -> None: ...
    def transcribe(self, audio: np.ndarray, language: str | None, is_cancelled: Callable[[], bool]) -> Any: ...
    def unload(self) -> None: ...


class AlignBackend(Protocol):
    def load(self) -> None: ...
    def align(self, audio: np.ndarray, text: str, language: str) -> list[Unit]: ...
    def unload(self) -> None: ...


@dataclass
class Engines:
    asr: Callable[[], AsrBackend]
    aligner: Callable[[], AlignBackend] | None  # None = 對齊模型未安裝
    read_audio: Callable[[Path], np.ndarray]
    #: 一次辨識幾段（ASR 實作有 transcribe_batch 時才會批次）
    asr_batch: int = 1


@dataclass
class PipelineResult:
    raw: list[dict[str, Any]]  # 每段：manifest 欄位 + language + text + file
    units: dict[int, list[Unit] | None]  # 每段的字／詞時間（段內時間）；None = 未對齊
    warnings: list[str] = field(default_factory=list)


def aligner_supports(language: str | None) -> bool:
    if language not in ALIGNER_LANGUAGES:
        return False
    dep = _ALIGNER_EXTRA_DEPS.get(language)
    if dep is None:
        return True
    try:
        __import__(dep)
        return True
    except ImportError:
        return False


Report = Callable[..., None]  # report(progress=?, stage=?, detail=?)


def recognize(
    manifest: dict[str, Any],
    audio_dir: Path,
    engines: Engines,
    language: str | None,
    report: Report,
    is_cancelled: Callable[[], bool],
) -> tuple[list[dict[str, Any]], list[str]]:
    """步驟 1：載入 ASR → 逐段辨識 → 卸載。回傳 (每段結果, 警告)。"""
    seg_meta = manifest["segments"]
    files = manifest["files"]
    total_seconds = sum(s["duration"] for s in seg_meta) or 1.0
    warnings: list[str] = []

    def check() -> None:
        if is_cancelled():
            raise Cancelled()

    report(stage="正在載入語音辨識模型", progress=0.0, detail="")
    asr = engines.asr()
    raw: list[dict[str, Any]] = []
    try:
        asr.load()
        check()
        done = 0.0
        batch = max(1, engines.asr_batch) if hasattr(asr, "transcribe_batch") else 1
        items = list(zip(seg_meta, files))
        i = 0
        while i < len(items):
            check()
            group = items[i : i + batch]
            first, last = group[0][0]["index"] + 1, group[-1][0]["index"] + 1
            report(stage="正在辨識語音", detail=f"第 {first} / {len(seg_meta)} 段" if first == last else f"第 {first}–{last} / {len(seg_meta)} 段")
            audios = [engines.read_audio(audio_dir / rel) for _, rel in group]
            if batch > 1:
                try:
                    results = asr.transcribe_batch(audios, language, is_cancelled)  # type: ignore[attr-defined]
                except (MemoryError, RuntimeError) as e:
                    if not isinstance(e, MemoryError) and "memory" not in str(e).lower():
                        raise
                    # 記憶體不夠一次處理多段：改回逐段，之後也不再批次
                    batch = 1
                    continue
            else:
                results = [asr.transcribe(audios[0], language, is_cancelled)]
            check()
            for (meta, rel), res in zip(group, results):
                if res.truncated:
                    warnings.append(f"第 {meta['index'] + 1} 段文字可能不完整（超過生成長度上限）。")
                raw.append({**meta, "language": res.language, "text": res.text, "file": rel})
                done += meta["duration"]
            report(progress=P_LOAD_ASR + (P_ASR - P_LOAD_ASR) * done / total_seconds)
            i += len(group)
    finally:
        asr.unload()  # 規格 §5.4：用完立即卸載，再載入下一個模型
    return raw, warnings


def segments_to_align(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in raw if s["text"] and aligner_supports(s["language"])]


def align(
    raw: list[dict[str, Any]],
    audio_dir: Path,
    engines: Engines,
    report: Report,
    is_cancelled: Callable[[], bool],
) -> tuple[dict[int, list[Unit] | None], list[str]]:
    """步驟 2：載入對齊模型 → 逐段對齊 → 卸載。回傳 (每段字詞時間, 警告)。"""
    units: dict[int, list[Unit] | None] = {s["index"]: None for s in raw}
    warnings: list[str] = []
    to_align = segments_to_align(raw)
    if engines.aligner is None or not to_align:
        return units, warnings
    if is_cancelled():
        raise Cancelled()
    report(stage="正在載入時間戳記對齊模型", progress=P_ASR, detail="")
    aligner = engines.aligner()
    try:
        aligner.load()
        align_total = sum(s["duration"] for s in to_align) or 1.0
        done = 0.0
        for n, s in enumerate(to_align, 1):
            if is_cancelled():
                raise Cancelled()
            report(stage="正在對齊時間戳記", detail=f"第 {n} / {len(to_align)} 段")
            try:
                units[s["index"]] = aligner.align(engines.read_audio(audio_dir / s["file"]), s["text"], s["language"])
            except Exception:  # noqa: BLE001 - 單段失敗不影響整體，退回估計時間
                warnings.append(f"第 {s['index'] + 1} 段無法對齊，時間為估計值。")
            done += s["duration"]
            report(progress=P_LOAD_ALIGN + (P_ALIGN - P_LOAD_ALIGN) * done / align_total)
    finally:
        aligner.unload()
    return units, warnings


def alignment_warnings(raw: list[dict[str, Any]], aligner_available: bool) -> list[str]:
    if not aligner_available:
        return ["尚未下載時間戳記對齊模型，時間為依字數估計。"]
    unsupported = sorted({s["language"] or "未知" for s in raw if s["text"] and not aligner_supports(s["language"])})
    return [f"{'、'.join(unsupported)} 不支援精確對齊，時間為依字數估計。"] if unsupported else []


def recognize_and_align(
    manifest: dict[str, Any],
    audio_dir: Path,
    engines: Engines,
    language: str | None,
    report: Report,
    is_cancelled: Callable[[], bool],
) -> PipelineResult:
    """在同一個程序中依序執行兩個步驟（測試用；正式路徑在兩個獨立的工作程序中分別執行）。"""
    raw, w1 = recognize(manifest, audio_dir, engines, language, report, is_cancelled)
    units, w2 = align(raw, audio_dir, engines, report, is_cancelled)
    if is_cancelled():
        raise Cancelled()
    return PipelineResult(raw=raw, units=units, warnings=w1 + w2 + alignment_warnings(raw, engines.aligner is not None))
