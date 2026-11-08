"""彙整所有 /api 路由。後續 Phase 的 router 都在這裡註冊。"""
from fastapi import APIRouter

from app.api import health, media, session, system, tasks

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(session.router)
api_router.include_router(media.router)
api_router.include_router(tasks.router)
