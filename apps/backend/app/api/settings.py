"""設定頁（規格 §12.4）。

GET  /api/settings            推論裝置、記憶體使用偏好
PUT  /api/settings            更新（存在 <userData>/settings.json，下次產生摘要／辨識時生效）
GET  /api/settings/storage    資料夾位置與暫存大小
POST /api/settings/cleanup    清除暫存（其他工作階段留下的檔案、YouTube 下載元件的快取）
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import app_settings, sessions
from app.core import user_settings
from app.models.store import dir_size
from app.schemas.settings import CleanupResult, SettingsBody, StorageInfo
from app.session.manager import safe_rmtree

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsBody)
def get_settings(request: Request) -> SettingsBody:
    s = user_settings.load(app_settings(request).data_dir)
    return SettingsBody(device=s.device, memory=s.memory)


@router.put("", response_model=SettingsBody)
def put_settings(request: Request, body: SettingsBody) -> SettingsBody:
    s = user_settings.save(app_settings(request).data_dir, user_settings.UserSettings(device=body.device, memory=body.memory))
    return SettingsBody(device=s.device, memory=s.memory)


def _ytdlp_cache(request: Request):  # noqa: ANN202
    return request.app.state.ytdlp.dir / "cache"


@router.get("/storage", response_model=StorageInfo)
def storage(request: Request) -> StorageInfo:
    cfg = app_settings(request)
    mgr = sessions(request)
    return StorageInfo(
        data_dir=str(cfg.data_dir),
        models_dir=str(cfg.models_root),
        current_session_bytes=sum(dir_size(d) for d in mgr.active_dirs()),
        stale_bytes=sum(dir_size(d) for d in mgr.inactive_dirs()),
        cache_bytes=dir_size(_ytdlp_cache(request)),
    )


@router.post("/cleanup", response_model=CleanupResult)
def cleanup(request: Request) -> CleanupResult:
    mgr = sessions(request)
    freed = 0
    for d in mgr.inactive_dirs():
        freed += dir_size(d)
        safe_rmtree(d, mgr.root)
    cache = _ytdlp_cache(request)
    if cache.is_dir():
        freed += dir_size(cache)
        safe_rmtree(cache, request.app.state.ytdlp.dir)
    return CleanupResult(freed_bytes=freed)
