"""POST /api/asr/transcribe、GET /api/transcript（規格 §10）。編輯逐字稿（/api/transcript/update）在後續 Phase。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import app_settings, require_session, sessions
from app.schemas.media import TaskCreated, TranscribeRequest, Transcript
from app.services.media import MediaError
from app.services.transcribe import start_transcription

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
