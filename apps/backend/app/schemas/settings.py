"""設定頁（規格 §12.4）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SettingsBody(BaseModel):
    device: Literal["auto", "cpu"] = "auto"
    memory: Literal["standard", "low"] = "standard"


class StorageInfo(BaseModel):
    data_dir: str
    models_dir: str
    #: 目前工作階段的暫存（匯入的影音、抽取的音訊）：換檔案或關閉程式時自動刪除
    current_session_bytes: int
    #: 其他工作階段留下的暫存（正常情況下啟動時就會清除）
    stale_bytes: int
    #: YouTube 下載元件的快取
    cache_bytes: int


class CleanupResult(BaseModel):
    freed_bytes: int
