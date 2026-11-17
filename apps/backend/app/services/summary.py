"""摘要工作（PROJECT_SPEC Phase 06、§4-E、§5.4、§5.5）。

輸入：本次 Session 的逐字稿（Phase 05）。
流程（背景執行緒，可隨時取消）：
    1. 啟動 llama-server 並載入摘要模型（與語音辨識不同時執行：MODEL_LOCK）
    2. 依使用者勾選的類型產生摘要；長逐字稿採分段＋階層式整合（app/engines/llm/summarize.py）
    3. 關閉 llama-server（模型記憶體完全釋放）
    4. 結果存在 Session（記憶體＋暫存資料夾的 summary.json，Session 結束即刪除，規格 §8.3）
取消：終止 llama-server 程序，生成立刻停止。
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.hardware import detect
from app.core.runtime_select import InsufficientMemory, LlmPlan, llm_options, plan_llm
from app.engines.llm.server import LlamaServer, LlmCancelled, LlmError, ServerOptions
from app.engines.llm.summarize import ALL_TYPES, Budget, Line, SummaryType, summarize
from app.models.registry import LLM_MODEL, gguf_path
from app.models.store import is_installed
from app.services.media import MediaError
from app.services.model_lock import BUSY_MESSAGE, MODEL_LOCK
from app.services.tasks import Task, TaskCancelled, UserFacingError
from app.session.manager import Session, SessionManager


# 回傳的物件：可用 with 開關（啟動／關閉模型）、chat()、可從其他執行緒 kill()（取消用）。測試可替換成假模型。
LlmFactory = Callable[[Settings], Any]

DOWNLOAD_HINT = "請到「模型管理」下載「摘要與心智圖」。"


class FallbackLlm:
    """依 Runtime Selector 的計畫啟動 llama-server（Phase 10）。GPU 啟動失敗（例如 VRAM 被其他程式佔用、驅動問題）時，
    自動改用 CPU 版再試一次（§5.4：GPU 記憶體不足時改用 CPU）。對外介面與 LlamaServer 相同：with、chat()、kill()。"""

    def __init__(self, plan: LlmPlan, model: Path, threads: int, make: Callable[[ServerOptions], Any] = LlamaServer) -> None:
        self.plan = plan
        self.model = model
        self.threads = threads
        self.make = make
        self.device = plan.device
        self.note = "；".join(plan.warnings)
        self.ctx_size = plan.ctx
        self._srv: Any = None
        self._killed = False

    def _options(self, exe: str, layers: int) -> ServerOptions:
        return ServerOptions(Path(exe), self.model, ctx_size=self.plan.ctx, threads=self.threads, extra_args=("--n-gpu-layers", str(layers)))

    def __enter__(self) -> FallbackLlm:
        assert self.plan.executable is not None
        self._srv = self.make(self._options(self.plan.executable, self.plan.n_gpu_layers))
        try:
            self._srv.__enter__()
        except LlmError as e:
            if self._killed or self.plan.device == "cpu" or not self.plan.cpu_executable:
                raise
            print(f"[llm] GPU ({self.plan.device}) failed to start, falling back to CPU: {e}", flush=True)
            self._srv = self.make(self._options(self.plan.cpu_executable, 0))
            self._srv.__enter__()
            self.device = "cpu"
            self.note = "；".join([*self.plan.warnings, "GPU 無法載入模型（可能是顯示記憶體不足），已改用 CPU。"])
        return self

    def __exit__(self, *exc: object) -> None:
        if self._srv is not None:
            self._srv.__exit__(*exc)

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        return self._srv.chat(*args, **kwargs)

    def kill(self) -> None:
        self._killed = True
        if self._srv is not None:
            self._srv.kill()


def default_llm(cfg: Settings) -> FallbackLlm:
    model = gguf_path(LLM_MODEL, cfg.models_root)
    try:
        plan = plan_llm(detect(), cfg.runtime_root, model, **llm_options(cfg))
    except InsufficientMemory as e:
        raise MediaError(507, str(e)) from None
    if plan.executable is None:
        raise MediaError(412, "尚未安裝 llama.cpp（摘要用的執行程式）。" + DOWNLOAD_HINT)
    print(f"[llm] device={plan.device} n_gpu_layers={plan.n_gpu_layers} ctx={plan.ctx} ({plan.reason})", flush=True)
    return FallbackLlm(plan, model, cfg.llm_threads)


def lines_from_transcript(transcript: dict[str, Any]) -> list[Line]:
    return [
        Line(int(s["id"]), float(s["start"]), float(s["end"]), str(s["text"]).strip())
        for s in transcript.get("segments", [])
        if str(s.get("text", "")).strip()
    ]


def parse_types(types: Sequence[str]) -> list[SummaryType]:
    chosen = [t for t in ALL_TYPES if t in set(types)]
    unknown = sorted(set(types) - set(ALL_TYPES))
    if unknown:
        raise MediaError(422, f"不支援的摘要類型：{'、'.join(unknown)}")
    if not chosen:
        raise MediaError(422, "請至少選擇一種摘要內容。")
    return chosen


def start_summary(
    cfg: Settings,
    sessions: SessionManager,
    session: Session,
    media_id: str,
    types: Sequence[str],
    llm_factory: LlmFactory = default_llm,
    merge: bool = False,
) -> Task:
    """merge=True：只重新產生指定的類型，保留現有摘要的其他內容（例如「重新產生心智圖」）。"""
    rec = session.media
    if rec is None or rec.id != media_id:
        raise MediaError(404, "找不到這個媒體，請重新匯入。")
    chosen = parse_types(types)
    busy = [t for t in sessions.tasks.for_session(session.id) if t.status in ("queued", "running")]
    if any(t.kind == "summarize" for t in busy):
        raise MediaError(409, "摘要已在產生中。")
    if any(t.kind in ("extract-audio", "transcribe") for t in busy):
        raise MediaError(409, "請等音訊抽取與語音辨識完成後再產生摘要。")
    transcript = rec.transcript
    if transcript is None:
        raise MediaError(409, "請先完成語音辨識，再產生摘要。")
    lines = lines_from_transcript(transcript)
    if not lines:
        raise MediaError(409, "逐字稿沒有內容，無法產生摘要。")
    if not is_installed(LLM_MODEL, cfg.models_root) and llm_factory is default_llm:
        raise MediaError(412, f"尚未下載摘要模型（{LLM_MODEL.display_name}）。" + DOWNLOAD_HINT)
    if not MODEL_LOCK.acquire(blocking=False):
        raise MediaError(409, BUSY_MESSAGE)
    try:
        llm = llm_factory(cfg)
    except Exception:
        MODEL_LOCK.release()
        raise
    previous = rec.summary if merge else None
    rec.summary = previous  # merge 時舊內容在產生期間仍可讀；否則清除
    # 記憶體不足時 Runtime Selector 會縮短 context（Phase 10）；摘要的分段大小跟著調整
    budget = Budget.for_ctx(getattr(llm, "ctx_size", cfg.llm_ctx))

    def job(task: Task) -> dict[str, Any]:
        started = time.monotonic()
        try:
            task.update(stage="正在載入摘要模型", progress=0.0)
            task.on_cancel(llm.kill)
            if task.cancelled:
                raise TaskCancelled()
            try:
                with llm:
                    if task.cancelled:
                        raise TaskCancelled()

                    def report(p: float, stage: str, detail: str) -> None:
                        if task.cancelled:
                            raise TaskCancelled()
                        task.update(progress=p, stage=stage, detail=detail)

                    out = summarize(llm, lines, chosen, budget, progress=report)
            except LlmCancelled as e:
                raise TaskCancelled() from e
            except LlmError as e:
                raise UserFacingError(str(e)) from e
            except ValueError as e:  # 模型輸出無法解析（重試後仍失敗）
                raise UserFacingError("摘要模型的輸出格式不正確，請再試一次。") from e
            if task.cancelled:
                raise TaskCancelled()
            elapsed = time.monotonic() - started
            results = {**(previous["results"] if previous else {}), **out["results"]}
            types_done = [t for t in ALL_TYPES if t in results]
            summary = {
                "media_id": rec.id,
                "types": types_done,
                "results": results,
                "model": f"{LLM_MODEL.repo}@{LLM_MODEL.revision[:7]}",
                "chunks": out["chunks"],
                "levels": out["levels"],
                "elapsed_seconds": round(elapsed, 1),
                # Phase 10：實際使用的運算裝置（GPU 失敗改用 CPU 時也會反映在這裡）
                "device": getattr(llm, "device", None),
                "device_note": getattr(llm, "note", None) or None,
            }
            (rec.dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
            rec.summary = summary
            task.update(stage="完成", progress=1.0, detail="")
            return {"media_id": rec.id, "types": out["types"], "chunks": out["chunks"], "levels": out["levels"], "elapsed_seconds": round(elapsed, 1)}
        finally:
            MODEL_LOCK.release()

    return sessions.tasks.start(session.id, "summarize", job)
