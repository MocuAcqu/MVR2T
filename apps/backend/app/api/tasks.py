"""GET /api/tasks/{task_id}、POST /api/tasks/{task_id}/cancel（規格 §10）。

規格要求所有工作 API 都帶 Session ID：這裡以 query 參數傳入，並確認工作屬於該 Session。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import require_session, tasks
from app.schemas.media import TaskState
from app.services.tasks import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get(request: Request, task_id: str, session_id: str) -> Task:
    require_session(request, session_id)
    task = tasks(request).get(task_id)
    if task is None or task.session_id != session_id:
        raise HTTPException(status_code=404, detail="找不到這個工作。")
    return task


@router.get("/{task_id}", response_model=TaskState)
def get_task(request: Request, task_id: str, session_id: str = Query(...)) -> TaskState:
    return TaskState(**_get(request, task_id, session_id).snapshot())


@router.post("/{task_id}/cancel", response_model=TaskState)
def cancel_task(request: Request, task_id: str, session_id: str = Query(...)) -> TaskState:
    task = _get(request, task_id, session_id)
    task.request_cancel()
    return TaskState(**task.snapshot())
