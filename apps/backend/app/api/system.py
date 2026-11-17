"""GET /api/system/ffmpeg：FFmpeg 是否可用；GET /api/system/info：硬體與運算裝置（Phase 10，規格 §6.4、§10）。"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import app_settings
from app.engines.media import ffmpeg as ff
from app.core.hardware import detect
from app.core.runtime_select import llm_options, plan_asr, plan_llm
from app.models.registry import LLM_MODEL, gguf_path
from app.schemas.media import FfmpegStatus, SystemInfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/ffmpeg", response_model=FfmpegStatus)
def ffmpeg_status(request: Request) -> FfmpegStatus:
    cfg = app_settings(request)
    loc = ff.locate_ffmpeg(cfg.ffmpeg_dir, cfg.runtime_ffmpeg_dir, cfg.bundled_ffmpeg_dir)
    if loc is None:
        return FfmpegStatus(available=False, version=None, source=None, ffmpeg_path=None)
    version = ff.ffmpeg_version(loc)
    return FfmpegStatus(available=version is not None, version=version, source=loc.source, ffmpeg_path=str(loc.ffmpeg))


@router.get("/info", response_model=SystemInfo)
def system_info(request: Request, refresh: bool = Query(False)) -> SystemInfo:
    """硬體資訊與目前的運算裝置。refresh=true 重新偵測顯示卡（例如剛更新驅動程式）。不連網。"""
    cfg = app_settings(request)
    hw = detect(refresh=refresh)
    llm = plan_llm(hw, cfg.runtime_root, gguf_path(LLM_MODEL, cfg.models_root), check_memory=False, **llm_options(cfg))
    return SystemInfo(hardware=hw.to_dict(), llm=llm.to_dict(), asr=plan_asr(hw).to_dict())  # type: ignore[arg-type]
