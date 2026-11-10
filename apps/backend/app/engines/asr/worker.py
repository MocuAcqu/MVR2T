"""在獨立的工作程序中執行語音辨識（真實模型的正式路徑）。

為什麼要另開程序（2026-11-09 實測）：在同一個程序中「卸載」模型後，記憶體不會還給作業系統
（ASR 卸載後仍佔約 3.2 GB，而且每辨識一次就再增加），違反規格 §5.4「依序載入、任務結束後釋放」。
工作程序結束時，作業系統會回收它的全部記憶體；模型記憶體不足而崩潰時，也只會結束工作程序，
後端仍正常運作並回報清楚的錯誤（規格 §5.4：不可直接崩潰）。

通訊：父程序傳入 job（只含路徑與設定，可被 pickle）、事件佇列與取消旗標；
子程序回傳 progress / done / cancelled / error 訊息。使用 spawn（Windows 唯一支援的方式），跨平台行為一致。
"""
from __future__ import annotations

import os
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 父程序結束時，子程序最多等這麼久就自行結束（避免成為孤兒）
_PARENT_POLL_SECONDS = 1.0


@dataclass(frozen=True)
class EngineSpec:
    """在子程序中重建模型所需的資訊（可被 pickle）。"""

    asr_dir: str
    aligner_dir: str | None
    dtype: str
    threads: int
    asr_batch: int = 4  # 一次辨識幾段（MVR2T_ASR_BATCH）


def _watch_parent() -> None:
    """父程序（後端）消失時立即結束，不留下佔用數 GB 記憶體的孤兒程序。"""
    import multiprocessing

    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch() -> None:
        from multiprocessing.connection import wait

        wait([parent.sentinel])
        os._exit(3)

    threading.Thread(target=watch, daemon=True, name="parent-watchdog").start()


def worker_main(phase: str, spec: EngineSpec, payload: dict[str, Any], events: Any, cancel: Any) -> None:
    """子程序進入點。phase = "asr"（辨識）或 "align"（對齊）。每個程序只載入一個模型，做完就結束，
    所以 ASR 的記憶體在對齊模型載入前已完全還給作業系統（規格 §5.4）。所有例外都轉成訊息送回父程序。"""
    _watch_parent()
    try:
        from dataclasses import asdict

        from app.engines.asr.pipeline import Cancelled, Engines, align, recognize
        from app.engines.asr.qwen3 import Qwen3Aligner, Qwen3Asr, read_wav_16k_mono

        engines = Engines(
            asr=lambda: Qwen3Asr(Path(spec.asr_dir), spec.dtype, spec.threads),
            aligner=(lambda: Qwen3Aligner(Path(spec.aligner_dir), spec.dtype, spec.threads)) if spec.aligner_dir else None,
            read_audio=read_wav_16k_mono,
            asr_batch=spec.asr_batch,
        )

        def report(**kw: Any) -> None:
            events.put({"type": "progress", **kw})

        audio_dir = Path(payload["audio_dir"])
        try:
            if phase == "asr":
                raw, warnings = recognize(payload["manifest"], audio_dir, engines, payload["language"], report, cancel.is_set)
                events.put({"type": "done", "raw": raw, "warnings": warnings})
            else:
                units, warnings = align(payload["raw"], audio_dir, engines, report, cancel.is_set)
                events.put(
                    {
                        "type": "done",
                        "units": {k: ([asdict(u) for u in v] if v is not None else None) for k, v in units.items()},
                        "warnings": warnings,
                    }
                )
        except Cancelled:
            events.put({"type": "cancelled"})
    except MemoryError:
        events.put({"type": "error", "message": "記憶體不足，無法完成語音辨識。請關閉其他程式後再試。"})
    except Exception as e:  # noqa: BLE001
        from app.engines.asr.qwen3 import EngineError

        msg = str(e) if isinstance(e, EngineError) else f"語音辨識發生錯誤：{e}"
        events.put({"type": "error", "message": msg})


class WorkerCrashed(Exception):
    pass


class WorkerCancelled(Exception):
    pass


class WorkerFailed(Exception):
    pass


def run_in_worker(
    phase: str,
    spec: EngineSpec,
    payload: dict[str, Any],
    report: Callable[..., None],
    is_cancelled: Callable[[], bool],
    on_start: Callable[[Callable[[], None]], None] | None = None,
) -> dict[str, Any]:
    """在新的子程序執行一個步驟（"asr" 或 "align"），回傳 done 訊息內容。

    on_start(kill)：讓呼叫端登記「立即終止子程序」的函式（例如 Session 結束、使用者取消）。
    """
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    events = ctx.Queue()
    cancel = ctx.Event()
    proc = ctx.Process(
        target=worker_main,
        args=(phase, spec, payload, events, cancel),
        name="mvr2t-asr-worker",
        daemon=True,
    )
    proc.start()

    def kill() -> None:
        cancel.set()
        if proc.is_alive():
            proc.terminate()

    if on_start:
        on_start(kill)

    cancel_sent_at: float | None = None
    try:
        while True:
            if is_cancelled() and cancel_sent_at is None:
                cancel.set()  # 請子程序在下一個 token 停下（優雅結束）
                cancel_sent_at = time.monotonic()
            if cancel_sent_at is not None and time.monotonic() - cancel_sent_at > 5 and proc.is_alive():
                proc.terminate()  # 5 秒內沒結束就強制終止
            try:
                msg = events.get(timeout=0.2)
            except queue.Empty:
                if not proc.is_alive():
                    # 讀完可能已送出但尚未取出的最後訊息
                    try:
                        msg = events.get(timeout=0.5)
                    except queue.Empty:
                        if is_cancelled():
                            raise WorkerCancelled() from None
                        raise WorkerCrashed(
                            f"語音辨識程序意外結束（代碼 {proc.exitcode}），可能是記憶體不足。請關閉其他程式後再試。"
                        ) from None
                else:
                    continue
            kind = msg.get("type")
            if kind == "progress":
                report(**{k: v for k, v in msg.items() if k != "type"})
            elif kind == "done":
                return msg
            elif kind == "cancelled":
                raise WorkerCancelled()
            elif kind == "error":
                raise WorkerFailed(msg["message"])
    finally:
        proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        events.close()
