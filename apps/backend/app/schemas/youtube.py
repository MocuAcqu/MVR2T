"""YouTube 連結（使用者決定 2026-11-15）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class YtDlpJob(BaseModel):
    phase: Literal["checking", "downloading", "installing"]
    done_bytes: int
    total_bytes: int
    cancelling: bool


class YtDlpLast(BaseModel):
    ok: bool
    message: str | None


class YtDlpState(BaseModel):
    installed: bool
    version: str | None
    installed_at: float | None
    supported: bool
    latest_version: str | None
    update_available: bool
    checked_at: float | None
    size_bytes: int | None
    license: str
    job: YtDlpJob | None
    last: YtDlpLast | None


class ProbeRequest(BaseModel):
    session_id: str
    url: str = Field(min_length=1, max_length=2048)


class SubtitleChoice(BaseModel):
    lang: str = Field(min_length=1, max_length=32)
    name: str = Field(max_length=200)


class YouTubeVideo(BaseModel):
    video_id: str
    url: str
    title: str
    channel: str | None
    duration: float | None
    audio_size: int | None
    subtitles: list[SubtitleChoice]


class DownloadRequest(BaseModel):
    session_id: str
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(default="YouTube 影片", max_length=1000)
    duration: float | None = None
    audio_size: int | None = None
    #: 使用影片作者提供的字幕；None = 之後用語音辨識
    subtitle: SubtitleChoice | None = None
