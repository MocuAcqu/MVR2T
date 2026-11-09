"""長時間工作的追蹤與取消（PROJECT_SPEC §10：Task ID 追蹤進度、支援取消）。

每個工作在背景執行緒中跑；Renderer 以 GET /api/tasks/{task_id} 輪詢進度
（本機呼叫、每 0.5 秒一次，負擔極小；EventSource 無法帶授權標頭，所以第一版不用 SSE）。

取消：設定 cancel_event，並呼叫工作登記的 on_cancel（例如終止 FFmpeg 子行程）。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.keepawake import KEEP_AWAKE, KeepAwake

TaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


@dataclass
class Task:
    id: str
    session_id: str
    kind: str
    status: TaskStatus = "queued"
    progress: float = 0.0  # 0 ~ 1，整體進度
    stage: str = ""  # 目前步驟（給使用者看的繁體中文）
    detail: str = ""  # 例如「第 3 / 12 段」
    message: str | None = None  # 失敗原因
    result: Any = None
    created_at: float = field(default_factory=time.time)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _on_cancel: list[Callable[[], None]] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)

    # --- 給工作函式使用 ---------------------------------------------------
    def update(self, *, progress: float | None = None, stage: str | None = None, detail: str | None = None) -> None:
        with self._lock:
            if progress is not None:
                self.progress = max(self.progress, min(1.0, progress))  # 進度只增不減
            if stage is not None:
                self.stage = stage
            if detail is not None:
                self.detail = detail

    def on_cancel(self, fn: Callable[[], None]) -> None:
        """登記取消時要執行的動作；若已取消則立即執行。"""
        with self._lock:
            self._on_cancel.append(fn)
            already = self.cancel_event.is_set()
        if already:
            fn()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    # --- 給管理者使用 ------------------------------------------------------
    def request_cancel(self) -> None:
        with self._lock:
            if self.status in TERMINAL:
                return
            self.cancel_event.set()
            callbacks = list(self._on_cancel)
        for fn in callbacks:
            try:
                fn()
            except Exception:  # noqa: BLE001 - 取消動作失敗不應影響其他清理
                pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "task_id": self.id,
                "session_id": self.session_id,
                "kind": self.kind,
                "status": self.status,
                "progress": round(self.progress, 4),
                "stage": self.stage,
                "detail": self.detail,
                "message": self.message,
                "result": self.result,
            }


class TaskCancelled(Exception):
    """工作函式在偵測到取消時丟出，由 TaskManager 轉為 cancelled 狀態。"""


class UserFacingError(Exception):
    """訊息可直接顯示給使用者的錯誤（繁體中文）。"""


class TaskManager:
    def __init__(self, keep_awake: KeepAwake | None = None) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        # 工作執行期間請系統不要因閒置而睡眠（見 app/core/keepawake.py）
        self._keep_awake = keep_awake if keep_awake is not None else KEEP_AWAKE

    def start(self, session_id: str, kind: str, fn: Callable[[Task], Any]) -> Task:
        task = Task(id=uuid.uuid4().hex, session_id=session_id, kind=kind)
        with self._lock:
            self._tasks[task.id] = task

        def runner() -> None:
            task.status = "running"
            self._keep_awake.acquire()
            try:
                result = fn(task)
                if task.cancelled:
                    raise TaskCancelled()
                task.result = result
                task.progress = 1.0
                task.status = "completed"
            except TaskCancelled:
                task.status = "cancelled"
                task.stage = "已取消"
            except UserFacingError as e:
                task.status = "failed"
                task.message = str(e)
            except Exception as e:  # noqa: BLE001
                task.status = "cancelled" if task.cancelled else "failed"
                task.message = None if task.cancelled else f"處理時發生未預期的錯誤：{e}"
            finally:
                self._keep_awake.release()

        task.thread = threading.Thread(target=runner, name=f"task-{kind}-{task.id[:8]}", daemon=True)
        task.thread.start()
        return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def for_session(self, session_id: str) -> list[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.session_id == session_id]

    def cancel_session(self, session_id: str, wait: float = 10.0) -> None:
        """取消並等待某個 Session 的所有工作結束（結束 Session 前必須呼叫，才能安全刪除暫存檔）。"""
        tasks = self.for_session(session_id)
        for t in tasks:
            t.request_cancel()
        deadline = time.monotonic() + wait
        for t in tasks:
            if t.thread is not None:
                t.thread.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            for t in tasks:
                self._tasks.pop(t.id, None)
