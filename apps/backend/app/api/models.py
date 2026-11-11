"""模型管理（PROJECT_SPEC §7、§10、Phase 09）。

GET    /api/models                       模型清單、安裝狀態、下載進度（下載中由前端輪詢）
GET    /api/models/legacy                Phase 05～08 的簡易清單（保留給舊畫面與腳本相容）
POST   /api/models/download-all          下載所有尚未安裝的模型
POST   /api/models/{package}/download    下載（或續傳、更新版本、修復）
POST   /api/models/{package}/verify      重新計算雜湊，檢查檔案完整
POST   /api/models/{package}/cancel      取消下載或驗證（已下載的部分保留）
DELETE /api/models/{package}             刪除模型（語音辨識或摘要使用中時不能刪）
DELETE /api/models/unused/{key}          刪除不再使用的模型或執行檔（舊版本、中斷的暫存）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import app_settings
from app.models.manager import ManagerError, ModelManager
from app.models.registry import ALL_MODELS
from app.models.runtime import LLAMA_CPP, find_llama_server
from app.models.store import is_installed
from app.schemas.media import ModelInfo, ModelManagerState, ModelsResponse, RuntimeInfo

router = APIRouter(tags=["models"])


def _manager(request: Request) -> ModelManager:
    return request.app.state.model_manager


def _run(fn) -> None:  # noqa: ANN001
    try:
        fn()
    except ManagerError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None


@router.get("/models", response_model=ModelManagerState)
def get_models(request: Request) -> ModelManagerState:
    return ModelManagerState(**_manager(request).snapshot())


@router.get("/models/legacy", response_model=ModelsResponse)
def list_models_legacy(request: Request) -> ModelsResponse:
    cfg = app_settings(request)
    root = cfg.models_root
    return ModelsResponse(
        runtimes=[RuntimeInfo(name="llama.cpp", version=LLAMA_CPP.tag, installed=find_llama_server(cfg.runtime_root) is not None)],
        models_dir=str(root),
        models=[
            ModelInfo(
                id=m.id,
                kind=m.kind,
                display_name=m.display_name,
                role=m.role,
                repo=m.repo,
                revision=m.revision,
                license=m.license,
                size_bytes=m.size_bytes,
                installed=m.downloadable and is_installed(m, root),
                downloadable=m.downloadable,
                available_from_phase=m.available_from_phase,
            )
            for m in ALL_MODELS
        ],
    )


@router.post("/models/download-all", response_model=ModelManagerState)
def download_all(request: Request) -> ModelManagerState:
    m = _manager(request)
    m.download_all()
    return ModelManagerState(**m.snapshot())


@router.post("/models/{package}/{action}", response_model=ModelManagerState)
def package_action(request: Request, package: str, action: str) -> ModelManagerState:
    m = _manager(request)
    if action == "download":
        _run(lambda: m.request(package, "download"))
    elif action == "verify":
        _run(lambda: m.request(package, "verify"))
    elif action == "cancel":
        _run(lambda: m.cancel(package))
    else:
        raise HTTPException(status_code=404, detail="沒有這個動作。")
    return ModelManagerState(**m.snapshot())


@router.delete("/models/unused/{key:path}", status_code=204)
def delete_unused(request: Request, key: str) -> Response:
    _run(lambda: _manager(request).delete_unused(key))
    return Response(status_code=204)


@router.delete("/models/{package}", status_code=204)
def delete_package(request: Request, package: str) -> Response:
    _run(lambda: _manager(request).delete(package))
    return Response(status_code=204)
