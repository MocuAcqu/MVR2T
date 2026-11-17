"""POST /api/asr/transcribe、GET /api/transcript、PUT /api/transcript（逐字稿編輯器，規格 §2.1-D、§10）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import app_settings, require_session, sessions
from app.schemas.media import TaskCreated, TranscribeRequest, Transcript, TranscriptUpdate
from app.services.media import MediaError
from app.services.transcribe import start_transcription, update_transcript

router = APIRouter(tags=["asr"])


@router.post("/asr/transcribe", response_model=TaskCreated)
def transcribe(request: Request, body: TranscribeRequest) -> TaskCreated:
    session = require_session(request, body.session_id)
    try:
        task = start_transcription(
            app_settings(request),
            sessions(request),
            session,
            body.media_id,
            body.language,
            request.app.state.engines_factory,
        )
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return TaskCreated(task_id=task.id)


@router.get("/transcript", response_model=Transcript)
def get_transcript(request: Request, session_id: str = Query(...), media_id: str = Query(...)) -> Transcript:
    session = require_session(request, session_id)
    rec = session.media
    if rec is None or rec.id != media_id or rec.transcript is None:
        raise HTTPException(status_code=404, detail="還沒有這個媒體的逐字稿。")
    return Transcript(**rec.transcript)


@router.put("/transcript", response_model=Transcript)
def put_transcript(request: Request, body: TranscriptUpdate) -> Transcript:
    """儲存編輯後的逐字稿（只存在本次 Session，規格 §8.3）。之後的摘要與匯出都使用編輯後的內容。"""
    session = require_session(request, body.session_id)
    try:
        transcript = update_transcript(sessions(request), session, body.media_id, [s.model_dump() for s in body.segments])
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return Transcript(**transcript)
