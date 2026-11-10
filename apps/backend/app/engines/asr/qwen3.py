"""Qwen3-ASR 與 Qwen3-ForcedAligner 的 Transformers 實作（PROJECT_SPEC §5.1 / §5.2 / §5.4）。

- 只從本機資料夾載入（local_files_only + HF_HUB_OFFLINE），執行期間絕不連網（規格：Offline-first）。
- torch / transformers 延後到真正載入模型時才 import：後端啟動不必等數秒，也讓沒裝 torch 的環境仍可跑其他功能與測試。
- 依序載入：呼叫端負責「ASR 用完 unload → 再 load 對齊模型」，unload 會釋放記憶體。
- 辨識可在生成途中取消（StoppingCriteria 每產生一個 token 檢查一次）。

實測（2026-11-09，沙盒 2 核 CPU）：float32 峰值約 5.3 GB、bfloat16 約 3.2 GB，兩者輸出相同。
bfloat16 在沒有原生 BF16 指令的 CPU 上可能比 float32 慢，所以預設 float32，可用 MVR2T_ASR_DTYPE 調整。
"""
from __future__ import annotations

import gc
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.engines.asr.text import Unit

# 必須在 import transformers 之前設定
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

SAMPLE_RATE = 16_000


class EngineError(Exception):
    """模型無法載入或執行（訊息給使用者看）。"""


@dataclass
class AsrResult:
    language: str | None  # 例如 "Chinese"、"English"；偵測不到時為 None
    text: str
    truncated: bool  # 生成長度達上限，文字可能不完整


def _torch_dtype(name: str) -> Any:
    import torch

    try:
        return {"float32": torch.float32, "bfloat16": torch.bfloat16, "float16": torch.float16}[name]
    except KeyError as e:
        raise EngineError(f"不支援的 dtype：{name}（可用 float32 / bfloat16 / float16）") from e


def _configure_threads(threads: int) -> None:
    import torch

    if threads > 0:
        torch.set_num_threads(threads)


def release_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():  # pragma: no cover - 沙盒沒有 GPU
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover
        pass


def max_new_tokens_for(seconds: float) -> int:
    """依音訊長度估計生成上限：中文口語約每秒 4～6 字，留足餘裕。"""
    return int(min(1024, 64 + seconds * 15))


class Qwen3Asr:
    def __init__(self, model_dir: Path, dtype: str = "float32", threads: int = 0) -> None:
        self.model_dir = model_dir
        self.dtype_name = dtype
        self.threads = threads
        self._model: Any = None
        self._processor: Any = None
        self._dtype: Any = None

    def load(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration
        except ImportError as e:
            raise EngineError("缺少語音辨識所需的套件（torch / transformers），請重新安裝後端套件。") from e
        _configure_threads(self.threads)
        self._dtype = _torch_dtype(self.dtype_name)
        try:
            self._processor = AutoProcessor.from_pretrained(self.model_dir, local_files_only=True)
            self._model = Qwen3ASRForConditionalGeneration.from_pretrained(
                self.model_dir, dtype=self._dtype, local_files_only=True
            ).eval()
        except (OSError, ValueError) as e:
            self.unload()
            raise EngineError(f"無法載入語音辨識模型：{e}") from e
        except MemoryError as e:
            self.unload()
            raise EngineError("記憶體不足，無法載入語音辨識模型。請關閉其他程式後再試。") from e

    def transcribe(self, audio: np.ndarray, language: str | None, is_cancelled: Callable[[], bool]) -> AsrResult:
        return self.transcribe_batch([audio], language, is_cancelled)[0]

    def transcribe_batch(
        self, audios: list[np.ndarray], language: str | None, is_cancelled: Callable[[], bool]
    ) -> list[AsrResult]:
        """一次辨識多段（同一次 generate）。沙盒（2 核）4 段一批快 1.7 倍；使用者的多核筆電上沒有明顯效益、
        尖峰記憶體多約 1.2 GB，所以預設不使用（docs/DEV_LOG.md「語音辨識加速」）。"""
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        class _Cancel(StoppingCriteria):
            def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> Any:
                return torch.full((input_ids.shape[0],), is_cancelled(), dtype=torch.bool)

        assert self._model is not None and self._processor is not None, "call load() first"
        n = len(audios)
        inputs = self._processor.apply_transcription_request(
            audio=audios if n > 1 else audios[0],
            language=([language] * n if n > 1 else language) if language else None,
        ).to(dtype=self._dtype)
        limits = [max_new_tokens_for(len(a) / SAMPLE_RATE) for a in audios]
        with torch.inference_mode():
            out = self._model.generate(
                **inputs, max_new_tokens=max(limits), do_sample=False, stopping_criteria=StoppingCriteriaList([_Cancel()])
            )
        pad_id = getattr(self._model.generation_config, "pad_token_id", None)
        results = []
        for i, limit in enumerate(limits):
            generated = out[i, inputs["input_ids"].shape[1] :]
            length = int((generated != pad_id).sum()) if pad_id is not None else len(generated)
            parsed = self._processor.decode(generated, return_format="parsed")
            # 強制指定語言時，模型不會再輸出語言標記，所以以指定的語言為準
            detected = parsed.get("language") or language
            results.append(AsrResult(language=detected, text=(parsed.get("transcription") or "").strip(), truncated=length >= limit))
        return results

    def unload(self) -> None:
        self._model = None
        self._processor = None
        release_memory()


class Qwen3Aligner:
    def __init__(self, model_dir: Path, dtype: str = "float32", threads: int = 0) -> None:
        self.model_dir = model_dir
        self.dtype_name = dtype
        self.threads = threads
        self._model: Any = None
        self._processor: Any = None
        self._dtype: Any = None

    def load(self) -> None:
        try:
            from transformers import AutoProcessor, Qwen3ASRForTokenClassification
        except ImportError as e:
            raise EngineError("缺少時間戳記對齊所需的套件（torch / transformers）。") from e
        _configure_threads(self.threads)
        self._dtype = _torch_dtype(self.dtype_name)
        try:
            self._processor = AutoProcessor.from_pretrained(self.model_dir, local_files_only=True)
            self._model = Qwen3ASRForTokenClassification.from_pretrained(
                self.model_dir, dtype=self._dtype, local_files_only=True
            ).eval()
        except (OSError, ValueError) as e:
            self.unload()
            raise EngineError(f"無法載入時間戳記對齊模型：{e}") from e
        except MemoryError as e:
            self.unload()
            raise EngineError("記憶體不足，無法載入時間戳記對齊模型。") from e

    def align(self, audio: np.ndarray, text: str, language: str) -> list[Unit]:
        import torch

        assert self._model is not None and self._processor is not None, "call load() first"
        if not text.strip():
            return []
        inputs, words = self._processor.prepare_forced_aligner_inputs(audio=audio, transcript=text, language=language)
        inputs = inputs.to(dtype=self._dtype)
        with torch.inference_mode():
            logits = self._model(**inputs).logits
        items = self._processor.decode_forced_alignment(
            logits, inputs["input_ids"], words, timestamp_token_id=self._model.config.timestamp_token_id
        )[0]
        return [Unit(str(i["text"]), float(i["start_time"]), float(i["end_time"])) for i in items]

    def unload(self) -> None:
        self._model = None
        self._processor = None
        release_memory()


def read_wav_16k_mono(path: Path) -> np.ndarray:
    """讀取 Phase 04 產生的 16 kHz 單聲道 PCM WAV，轉為 float32 [-1, 1]。"""
    import wave

    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise EngineError(f"音訊格式不符（需要 16 kHz 單聲道 16-bit）：{path.name}")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
