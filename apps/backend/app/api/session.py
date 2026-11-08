"""POST /api/session、DELETE /api/session/{session_id}（規格 §10）。"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.api.deps import require_session, sessions
from app.schemas.media import SessionResponse

router = APIRouter(tags=["session"])


@router.post("/session", response_model=SessionResponse)
async def create_session(request: Request) -> SessionResponse:
    # 單一視窗程式：建立新 Session 會結束舊的並刪除暫存（重新整理 = 清空）
    s = await run_in_threadpool(sessions(request).create)
    return SessionResponse(session_id=s.id)


@router.delete("/session/{session_id}", status_code=204)
async def end_session(request: Request, session_id: str) -> Response:
    require_session(request, session_id)
    await run_in_threadpool(sessions(request).end, session_id)
    return Response(status_code=204)
