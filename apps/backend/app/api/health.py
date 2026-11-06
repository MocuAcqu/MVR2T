"""GET /api/health — 讓 Renderer / Electron 確認後端已就緒。"""
from __future__ import annotations

import platform
import sys

from fastapi import APIRouter

from app.core.config import APP_NAME, APP_VERSION
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=APP_NAME,
        version=APP_VERSION,
        platform=sys.platform,
        python_version=platform.python_version(),
    )
