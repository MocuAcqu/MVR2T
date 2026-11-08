"""POST /api/media/upload、POST /api/media/extract-audio（規格 §10）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.requests import ClientDisconnect

from app.api.deps import app_settings, require_session, sessions
from app.schemas.media import ExtractAudioRequest, MediaInfo, TaskCreated
from app.services import media as media_service

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/upload", response_model=MediaInfo)
async def upload_media(
    request: Request,
    session_id: str = Query(...),
    filename: str = Query(..., min_length=1, max_length=1024),
) -> MediaInfo:
    """請求本文是檔案的原始位元組（application/octet-stream），以串流寫入 Session 暫存。

    不用 multipart：避免先寫到系統暫存再複製一次，幾 GB 的影片也只寫一次。
    """
    session = require_session(request, session_id)
    raw_len = request.headers.get("content-length")
    try:
        content_length = int(raw_len) if raw_len is not None else None
    except ValueError:
        content_length = None
    try:
        rec = await media_service.import_media(
            app_settings(request), sessions(request), session, filename, content_length, request.stream()
        )
    except media_service.MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    except ClientDisconnect:
        # 使用者取消上傳；import_media 已清除部分寫入的檔案
        raise HTTPException(status_code=499, detail="上傳已取消。") from None
    return MediaInfo(**rec.info)


@router.post("/extract-audio", response_model=TaskCreated)
def extract_audio(request: Request, body: ExtractAudioRequest) -> TaskCreated:
    session = require_session(request, body.session_id)
    try:
        task = media_service.start_extraction(app_settings(request), sessions(request), session, body.media_id)
    except media_service.MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e
    return TaskCreated(task_id=task.id)
