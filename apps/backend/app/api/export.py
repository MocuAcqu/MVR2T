"""匯出（PROJECT_SPEC §G、Phase 08）。回傳檔案內容；存到哪裡由 Electron 的對話框決定。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import require_session
from app.schemas.media import ExportRequest
from app.services.export import ExportError, ExportSource, build_export, decode_png

router = APIRouter(tags=["export"])


@router.post("/export")
def export(request: Request, body: ExportRequest) -> Response:
    session = require_session(request, body.session_id)
    rec = session.media
    if rec is None or rec.id != body.media_id:
        raise HTTPException(status_code=404, detail="找不到這個媒體，請重新匯入。")
    try:
        src = ExportSource(
            filename=rec.display_name,
            duration=float(rec.info.get("duration") or 0),
            audio=rec.audio,
            audio_dir=rec.dir / "audio" if rec.audio else None,
            transcript=rec.transcript,
            summary=rec.summary,
            mindmap=body.mindmap.model_dump() if body.mindmap else None,
            mindmap_png=decode_png(body.mindmap_png),
        )
        data, media_type = build_export(src, body.content, body.format)
    except ExportError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "no-store"})
