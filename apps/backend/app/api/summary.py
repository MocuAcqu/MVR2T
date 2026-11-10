"""POST /api/summary/generate、GET /api/summary（規格 §10）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import app_settings, require_session, sessions
from app.schemas.media import Summary, SummaryRequest, TaskCreated
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
