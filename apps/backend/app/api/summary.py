"""POST /api/summary/generate、POST /api/mindmap/generate、GET /api/summary（規格 §10）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import app_settings, require_session, sessions
from app.schemas.media import MindMapRequest, Summary, SummaryRequest, TaskCreated
from app.services.media import MediaError
from app.services.summary import start_summary

router = APIRouter(tags=["summary"])


@router.post("/summary/generate", response_model=TaskCreated)
def generate(request: Request, body: SummaryRequest) -> TaskCreated:
    session = require_session(request, body.session_id)
    try:
        task = start_summary(
            app_settings(request), sessions(request), session, body.media_id, body.types, request.app.state.llm_factory
        )
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return TaskCreated(task_id=task.id)


@router.get("/summary", response_model=Summary)
def get_summary(request: Request, session_id: str = Query(...), media_id: str = Query(...)) -> Summary:
    session = require_session(request, session_id)
    rec = session.media
    if rec is None or rec.id != media_id or rec.summary is None:
        raise HTTPException(status_code=404, detail="還沒有這個媒體的摘要。")
    return Summary(**rec.summary)


@router.post("/mindmap/generate", response_model=TaskCreated)
def generate_mindmap(request: Request, body: MindMapRequest) -> TaskCreated:
    """只重新產生心智圖，保留已產生的其他摘要內容（心智圖本身也可以在「產生摘要」時一起勾選）。"""
    session = require_session(request, body.session_id)
    try:
        task = start_summary(
            app_settings(request), sessions(request), session, body.media_id, ["mindmap"], request.app.state.llm_factory, merge=True
        )
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return TaskCreated(task_id=task.id)
