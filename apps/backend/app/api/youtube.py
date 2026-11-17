"""YouTube 連結（使用者決定 2026-11-15）。

GET    /api/youtube/component              YouTube 下載元件（yt-dlp）的狀態
POST   /api/youtube/component/install      安裝或更新到官方最新版（例外於「依賴至少 2 週」規則）
POST   /api/youtube/component/check        查詢最新版本
POST   /api/youtube/component/cancel       取消下載
DELETE /api/youtube/component              刪除元件
POST   /api/youtube/probe                  讀取影片資訊（標題、長度、作者上傳的字幕）
POST   /api/youtube/download               只下載音訊（＋選擇的字幕）到 Session 暫存 → 背景工作
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import app_settings, require_session, sessions
from app.models.ytdlp import YtDlpComponent, YtDlpError
from app.schemas.media import TaskCreated
from app.schemas.youtube import DownloadRequest, ProbeRequest, YouTubeVideo, YtDlpState
from app.services import youtube as yt
from app.services.media import MediaError

router = APIRouter(prefix="/youtube", tags=["youtube"])


def _component(request: Request) -> YtDlpComponent:
    return request.app.state.ytdlp


def _state(request: Request) -> YtDlpState:
    return YtDlpState(**_component(request).snapshot())


@router.get("/component", response_model=YtDlpState)
def get_component(request: Request) -> YtDlpState:
    return _state(request)


@router.post("/component/{action}", response_model=YtDlpState)
def component_action(request: Request, action: str) -> YtDlpState:
    comp = _component(request)
    try:
        if action == "install":
            comp.install()
        elif action == "check":
            comp.check()
        elif action == "cancel":
            comp.cancel()
        else:
            raise HTTPException(status_code=404, detail="沒有這個動作。")
    except YtDlpError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None
    return _state(request)


@router.delete("/component", status_code=204)
def delete_component(request: Request) -> Response:
    try:
        _component(request).delete(yt.youtube_busy(sessions(request)))
    except YtDlpError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None
    return Response(status_code=204)


@router.post("/probe", response_model=YouTubeVideo)
def probe(request: Request, body: ProbeRequest) -> YouTubeVideo:
    require_session(request, body.session_id)
    try:
        return YouTubeVideo(**yt.probe_video(app_settings(request), _component(request), body.url))
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None


@router.post("/download", response_model=TaskCreated)
def download(request: Request, body: DownloadRequest) -> TaskCreated:
    session = require_session(request, body.session_id)
    try:
        task = yt.start_download(
            app_settings(request),
            sessions(request),
            session,
            _component(request),
            body.url,
            body.title,
            body.subtitle.model_dump() if body.subtitle else None,
            body.duration,
            body.audio_size,
        )
    except MediaError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from None
    return TaskCreated(task_id=task.id)
