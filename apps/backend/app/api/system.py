"""GET /api/system/ffmpeg：FFmpeg 是否可用（硬體資訊 /api/system/info 在 Phase 10）。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import app_settings
from app.engines.media import ffmpeg as ff
from app.schemas.media import FfmpegStatus

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/ffmpeg", response_model=FfmpegStatus)
def ffmpeg_status(request: Request) -> FfmpegStatus:
    cfg = app_settings(request)
    loc = ff.locate_ffmpeg(cfg.ffmpeg_dir, cfg.runtime_ffmpeg_dir)
    if loc is None:
        return FfmpegStatus(available=False, version=None, source=None, ffmpeg_path=None)
    version = ff.ffmpeg_version(loc)
    return FfmpegStatus(available=version is not None, version=version, source=loc.source, ffmpeg_path=str(loc.ffmpeg))
