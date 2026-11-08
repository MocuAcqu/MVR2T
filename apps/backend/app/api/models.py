"""GET /api/models：模型清單與安裝狀態（規格 §10；下載與刪除在 Phase 09）。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import app_settings
from app.models.registry import ALL_MODELS
from app.models.store import is_installed
from app.schemas.media import ModelInfo, ModelsResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsResponse)
def list_models(request: Request) -> ModelsResponse:
    root = app_settings(request).models_root
    return ModelsResponse(
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
