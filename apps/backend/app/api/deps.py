"""共用相依：取得 Session、Task 管理器，並把領域錯誤轉成 HTTP 回應。"""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.config import Settings

from app.services.tasks import TaskManager
from app.session.manager import Session, SessionManager


def app_settings(request: Request) -> Settings:
    """本 app 實例的設定（測試可傳入不同設定，不使用模組層級的全域值）。"""
    return request.app.state.settings


def sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


def tasks(request: Request) -> TaskManager:
    return request.app.state.tasks


def require_session(request: Request, session_id: str) -> Session:
    s = sessions(request).get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="工作階段已結束，請重新匯入檔案。")
    return s
