"""POST /api/media/upload、POST /api/media/extract-audio、GET /api/media/file（工作區播放器）（規格 §10、§12.4）。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
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


MEDIA_TYPES = {
    "mp4": "video/mp4", "mov": "video/quicktime", "mkv": "video/x-matroska", "webm": "video/webm",
    "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "flac": "audio/flac", "aac": "audio/aac", "ogg": "audio/ogg",
}


@router.get("/file")
def media_file(
    request: Request,
    session_id: str = Query(...),
    media_id: str = Query(...),
    kind: Literal["original", "audio"] = Query("original"),
) -> FileResponse:
    """工作區播放器：本次 Session 的原始影音（或抽取的 16 kHz 音訊，原始格式無法播放時使用）。支援 Range（拖曳進度）。

    <video>／<audio> 不能帶 Authorization 標頭，所以這個路徑也接受網址上的 token（見 core/security.py）。
    """
    session = require_session(request, session_id)
    rec = session.media
    if rec is None or rec.id != media_id:
        raise HTTPException(status_code=404, detail="找不到這個媒體，請重新匯入。")
    if kind == "audio":
        path = rec.dir / "audio" / "audio.wav"
        media_type = "audio/wav"
    else:
        path, media_type = rec.path, MEDIA_TYPES.get(rec.ext, "application/octet-stream")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="檔案不存在（可能還沒抽取音訊）。")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})
