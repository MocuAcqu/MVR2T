"""Batched speech recognition (pipeline.recognize with Engines.asr_batch)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from app.engines.asr.pipeline import Cancelled, Engines, recognize


@dataclass
class Res:
    language: str
    text: str
    truncated: bool = False


class BatchAsr:
    def __init__(self, oom_at: int | None = None) -> None:
        self.calls: list[int] = []
        self.oom_at = oom_at

    def load(self) -> None: ...
    def unload(self) -> None: ...

    def transcribe(self, audio, language, is_cancelled):  # noqa: ANN001, ANN201
        self.calls.append(1)
        return Res("Chinese", f"段{int(audio[0])}")

    def transcribe_batch(self, audios, language, is_cancelled):  # noqa: ANN001, ANN201
        if self.oom_at is not None and len(audios) > 1:
            raise RuntimeError("DefaultCPUAllocator: not enough memory: you tried to allocate 1 GB")
        self.calls.append(len(audios))
        return [Res("Chinese", f"段{int(a[0])}", truncated=int(a[0]) == 5) for a in audios]


def manifest(n: int) -> dict:
    return {
        "segments": [{"index": i, "start": i * 30.0, "end": (i + 1) * 30.0, "duration": 30.0} for i in range(n)],
        "files": [f"seg_{i}.wav" for i in range(n)],
    }


def engines(asr, batch: int) -> Engines:  # noqa: ANN001
    return Engines(asr=lambda: asr, aligner=None, read_audio=lambda p: np.array([float(p.stem.split("_")[1])]), asr_batch=batch)


def test_segments_are_recognized_in_batches_and_kept_in_order():
    asr = BatchAsr()
    details: list[str] = []
    raw, warnings = recognize(manifest(10), Path("."), engines(asr, 4), None, lambda **kw: details.append(kw.get("detail", "")), lambda: False)
    assert asr.calls == [4, 4, 2]
    assert [r["text"] for r in raw] == [f"段{i}" for i in range(10)]
    assert [r["index"] for r in raw] == list(range(10))
    assert "第 1–4 / 10 段" in details and "第 9–10 / 10 段" in details
    assert warnings == ["第 6 段文字可能不完整（超過生成長度上限）。"]


def test_out_of_memory_in_a_batch_falls_back_to_one_segment_at_a_time():
    asr = BatchAsr(oom_at=0)
    raw, _ = recognize(manifest(5), Path("."), engines(asr, 4), None, lambda **kw: None, lambda: False)
    assert asr.calls == [1, 1, 1, 1, 1]
    assert [r["text"] for r in raw] == [f"段{i}" for i in range(5)]


def test_batch_of_one_or_engines_without_batch_support_use_plain_transcribe():
    asr = BatchAsr()
    recognize(manifest(3), Path("."), engines(asr, 1), None, lambda **kw: None, lambda: False)
    assert asr.calls == [1, 1, 1]


def test_cancel_between_batches():
    asr = BatchAsr()
    state = {"n": 0}

    def cancelled() -> bool:
        return len(asr.calls) >= 1

    with pytest.raises(Cancelled):
        recognize(manifest(10), Path("."), engines(asr, 4), None, lambda **kw: None, cancelled)
    assert asr.calls == [4]
    assert state["n"] == 0


def test_batching_is_off_by_default(monkeypatch):
    """No measurable gain on the user's multi-core laptop and ~1.2 GB more memory (2026-11-11): default is one segment at a time."""
    from app.core.config import Settings

    monkeypatch.delenv("MVR2T_ASR_BATCH", raising=False)
    assert Settings().asr_batch == 1
    monkeypatch.setenv("MVR2T_ASR_BATCH", "4")
    assert Settings().asr_batch == 4
