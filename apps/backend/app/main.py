"""FastAPI 進入點。

由 Electron 啟動（正常路徑，見 apps/desktop/electron/backend.ts），或開發時手動啟動：
    cd apps/backend
    python -m app.main
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import APP_NAME, APP_VERSION, READY_MARKER, Settings, settings
from app.core.security import TokenAuthMiddleware
from app.services.tasks import TaskManager
from app.services.transcribe import default_engines
from app.session.manager import SessionManager


def create_app(cfg: Settings = settings) -> FastAPI:
    # 由 Electron 啟動時關閉互動式 API 文件，減少暴露面；手動開發時保留。
    docs_enabled = not cfg.auth_required
    task_manager = TaskManager()
    session_manager = SessionManager(cfg.sessions_root, task_manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # 規格 §8.4：啟動時清除上次異常結束留下的暫存；正常結束時清除本次暫存。
        removed = session_manager.cleanup_stale()
        if removed:
            print(f"Removed {removed} stale session folder(s)", flush=True)
        yield
        session_manager.end_all()

    app = FastAPI(
        lifespan=lifespan,
        title=APP_NAME,
        version=APP_VERSION,
        docs_url="/api/docs" if docs_enabled else None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        redoc_url=None,
    )

    # 注意順序：Starlette 最後加入的 middleware 在最外層。
    # 先加憑證驗證、再加 CORS，讓 CORS 在最外層：preflight 先被處理，401 回應也帶有 CORS 標頭。
    if cfg.auth_required:
        app.add_middleware(TokenAuthMiddleware, token=cfg.auth_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.state.settings = cfg
    app.state.engines_factory = default_engines  # 測試可替換成假模型
    app.state.tasks = task_manager
    app.state.sessions = session_manager
    app.include_router(api_router)
    return app


app = create_app()


def _bind_socket(host: str, port: int) -> socket.socket:
    """自行綁定連接埠。port=0 時由作業系統挑選空閒埠，沒有「先查再用」的競爭問題。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":
        # Windows 的 SO_REUSEADDR 語意不同（允許搶占），只在 POSIX 使用。
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def _announce_ready(port: int) -> None:
    """告訴 Electron 實際埠號。只輸出 ASCII，避免 Windows cp950 編碼問題。"""
    print(f"{READY_MARKER} {json.dumps({'port': port, 'pid': os.getpid()})}", flush=True)


_STDIN_POLL_SECONDS = 0.5


def _wait_stdin_eof_windows_pipe(fd: int) -> None:
    """Windows：以 PeekNamedPipe 輪詢 stdin 管線，直到 Electron 那端關閉。

    不能在執行緒中阻塞讀取：Windows 上一個執行緒對管線發出同步讀取時，其他對同一管線的操作都會被擋住。
    multiprocessing（spawn）啟動的語音辨識工作程序沿用這個 stdin，啟動時檢查它就會永遠卡住
    （2026-11-09 Windows 驗收：辨識停在「準備中 0%」）。PeekNamedPipe 不會留下等待中的讀取。
    """
    import ctypes
    import msvcrt
    import time
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.PeekNamedPipe.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.PeekNamedPipe.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(fd)
    available = wintypes.DWORD()
    while True:
        if not kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
            # 通常是 ERROR_BROKEN_PIPE（Electron 結束）；其他錯誤也代表管線已不可用，一樣結束後端
            return
        if available.value:
            os.read(fd, available.value)  # Electron 不會寫入資料；收到也直接丟棄（有資料時不會阻塞）
        time.sleep(_STDIN_POLL_SECONDS)


def _stdin_is_windows_pipe(fd: int) -> bool:
    """stdin 是否為 Windows 管線（Electron 啟動時是）。判斷不出來時回傳 False，退回原本的阻塞讀取。

    依 app/core/procmem.py 的原則：使用私有 WinDLL 並宣告型別。未宣告時 HANDLE 會被當成 32 位元 int 傳入，
    在 64 位元 Windows 上可能無聲失敗。
    """
    if sys.platform != "win32":
        return False
    import ctypes
    import msvcrt
    from ctypes import wintypes

    file_type_unknown, file_type_pipe = 0, 3
    try:
        handle = msvcrt.get_osfhandle(fd)
    except OSError:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    kernel32.GetFileType.restype = wintypes.DWORD
    ctypes.set_last_error(0)  # FILE_TYPE_UNKNOWN 只有在 GetLastError 非 0 時才代表失敗
    file_type = kernel32.GetFileType(handle)
    if file_type == file_type_unknown and ctypes.get_last_error() != 0:
        return False
    return file_type == file_type_pipe


def _wait_stdin_eof() -> None:
    """阻擋直到 stdin 讀到 EOF（Electron 結束時管線關閉）。"""
    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        return  # 沒有可用的 stdin：視同已關閉
    try:
        if _stdin_is_windows_pipe(fd):
            _wait_stdin_eof_windows_pipe(fd)
            return
        while sys.stdin.buffer.read(1024):
            pass  # Electron 不會寫入資料；收到也直接忽略
    except (OSError, ValueError):
        pass


def _watch_stdin(server: uvicorn.Server) -> None:
    """Electron 結束（正常關閉或當機）時 stdin 管線會關閉 → 偵測到 EOF → 後端優雅結束。"""
    _wait_stdin_eof()
    # 順序很重要：Electron 當機時 stdout 管線也已斷開，print 會丟出 BrokenPipeError。
    # 所以先排定保險計時器並要求 uvicorn 結束，最後才嘗試輸出訊息。
    # 保險：若 5 秒內沒結束（例如卡在請求中），直接結束行程。
    timer = threading.Timer(5.0, lambda: os._exit(0))
    timer.daemon = True
    timer.start()
    server.should_exit = True
    try:
        print("stdin closed, shutting down backend", flush=True)
    except (OSError, ValueError):
        pass


def run(cfg: Settings = settings) -> None:
    # 規格 §3.3 / §11-5：host 固定 127.0.0.1
    sock = _bind_socket(cfg.host, cfg.port)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="info"))

    if cfg.exit_on_stdin_eof:
        threading.Thread(target=_watch_stdin, args=(server,), daemon=True, name="stdin-watchdog").start()
    if not cfg.auth_required:
        print(f"Dev mode (no session token). API docs: http://{cfg.host}:{port}/api/docs", flush=True)

    _announce_ready(port)
    server.run(sockets=[sock])


if __name__ == "__main__":
    run()
