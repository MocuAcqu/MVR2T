"""後端設定。

所有設定都從環境變數讀取並提供安全預設值。

兩種啟動方式：
1. 由 Electron 啟動（Phase 03 起的正常路徑）：
   - MVR2T_BACKEND_PORT=0        → 由作業系統挑選空閒連接埠，啟動後在 stdout 回報實際埠號
   - MVR2T_AUTH_TOKEN=<隨機值>    → 一次性連線憑證，所有 /api 請求都必須帶上
   - MVR2T_ALLOWED_ORIGINS=...   → 只允許 Electron 視窗的來源
   - MVR2T_EXIT_ON_STDIN_EOF=1   → Electron 結束（含當機）時 stdin 關閉，後端隨之結束
2. 開發者手動執行 `python -m app.main`（Phase 01 的方式，仍保留以便單獨除錯後端）：
   固定 127.0.0.1:8765、不驗證憑證、開放 /api/docs。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

APP_NAME = "MVR2T - Local Media Studio"
APP_VERSION = "0.1.0"

# Electron 讀取 stdout 時用來辨識「後端已綁定連接埠」的標記（需與 electron/backend.ts 一致）。
READY_MARKER = "MVR2T_BACKEND_READY"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    # 規格 §3.3：後端僅監聽 127.0.0.1，不得預設監聽 0.0.0.0（刻意不提供環境變數覆寫）
    host: str = "127.0.0.1"
    port: int = field(default_factory=lambda: int(os.environ.get("MVR2T_BACKEND_PORT", "8765")))

    # 一次性連線憑證（規格 §3.3）。空字串 = 開發者手動啟動，不驗證。
    auth_token: str = field(default_factory=lambda: os.environ.get("MVR2T_AUTH_TOKEN", ""))

    # 允許的前端來源。開發：Vite dev server；正式版 file:// 頁面的 Origin 為 "null"，由 Electron 傳入。
    allowed_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.environ.get(
                "MVR2T_ALLOWED_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            )
        )
    )

    # Electron 用 stdin 管線綁定後端生命週期。
    exit_on_stdin_eof: bool = field(default_factory=lambda: _env_flag("MVR2T_EXIT_ON_STDIN_EOF"))

    @property
    def auth_required(self) -> bool:
        return bool(self.auth_token)


settings = Settings()
