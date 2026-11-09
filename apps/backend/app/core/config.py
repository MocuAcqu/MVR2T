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
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "MVR2T - Local Media Studio"
APP_VERSION = "0.1.0"

# Electron 讀取 stdout 時用來辨識「後端已綁定連接埠」的標記（需與 electron/backend.ts 一致）。
READY_MARKER = "MVR2T_BACKEND_READY"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


APP_DIR_NAME = "MVR2T"  # 需與 apps/desktop/package.json 的 productName 一致（Electron userData 資料夾名稱）


def default_user_data_dir() -> Path:
    """與 Electron app.getPath('userData') 相同的位置，讓手動啟動的後端與下載腳本使用同一份模型。

    Windows：%APPDATA%\\MVR2T　macOS：~/Library/Application Support/MVR2T　Linux：~/.config/MVR2T
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR_NAME


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

    # 應用程式資料目錄（規格 §7.3）。Electron 傳入 app.getPath('userData')。
    # Session 暫存放在 <data_dir>/temp/sessions/<session_id>/，結束 Session 或下次啟動時清除。
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ["MVR2T_DATA_DIR"]) if os.environ.get("MVR2T_DATA_DIR") else default_user_data_dir()
    )

    # 使用者在設定中指定的 FFmpeg 資料夾（含 ffmpeg 與 ffprobe）。空字串 = 自動尋找。
    ffmpeg_dir: str = field(default_factory=lambda: os.environ.get("MVR2T_FFMPEG_DIR", ""))

    # 匯入檔案大小上限（規格 §11-9）。需與 shared/constants/media.ts 的 MAX_MEDIA_BYTES 一致。
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.environ.get("MVR2T_MAX_UPLOAD_BYTES", str(10 * 1024**3)))
    )

    # 語音辨識的數值精度（float32 / bfloat16）。bfloat16 記憶體約減半，但在沒有原生 BF16 指令的 CPU 上可能較慢。
    asr_dtype: str = field(default_factory=lambda: os.environ.get("MVR2T_ASR_DTYPE", "float32"))
    # PyTorch 執行緒數；0 = 由 PyTorch 自動決定
    torch_threads: int = field(default_factory=lambda: int(os.environ.get("MVR2T_TORCH_THREADS", "0")))

    @property
    def sessions_root(self) -> Path:
        return self.data_dir / "temp" / "sessions"

    # 模型資料夾（可選）。未設定時為 <userData>/models；例如想把 3.4 GB 的模型放在 D 槽時設定 MVR2T_MODELS_DIR。
    models_dir: Path | None = field(
        default_factory=lambda: Path(os.environ["MVR2T_MODELS_DIR"]) if os.environ.get("MVR2T_MODELS_DIR") else None
    )

    @property
    def models_root(self) -> Path:
        """模型資料夾（規格 §7.3）：<models_dir 或 userData/models>/<kind>/<id>/"""
        return self.models_dir if self.models_dir is not None else self.data_dir / "models"

    @property
    def runtime_ffmpeg_dir(self) -> Path:
        return self.data_dir / "runtime" / "ffmpeg"

    @property
    def auth_required(self) -> bool:
        return bool(self.auth_token)


settings = Settings()
