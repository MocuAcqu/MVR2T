"""處理中防止電腦因閒置而睡眠（Windows：PowerRequestSystemRequired）。

為什麼在後端做：Electron 的 powerSaveBlocker('prevent-app-suspension') 在 Windows 8 以後對應的是
PowerRequestExecutionRequired（只讓程式不被暫停），**不會**阻止系統閒置睡眠；而 'prevent-display-sleep' 會讓螢幕也一直亮著。
2026-11-09 使用者實測 `powercfg /requests`：electron.exe 只出現在「執行」，SYSTEM 區段是空的。
所以由後端在工作執行期間另外送出 SYSTEM 請求；`powercfg /requests` 會在 SYSTEM 區段看到 python.exe 與下面的原因文字。

多個工作同時進行時以參考計數管理：第一個工作開始時送出請求，最後一個結束時清除。
請求失敗只記錄警告、不影響工作本身（睡眠時工作會暫停，喚醒後繼續）。

ctypes 原則同 app/core/procmem.py：私有 WinDLL、宣告 argtypes/restype、檢查回傳值。
"""
from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

REASON = "MVR2T：正在處理影音（抽取音訊／語音辨識）"


class _Backend(Protocol):
    def enable(self) -> None: ...
    def disable(self) -> None: ...


class _NoopBackend:
    """macOS / Linux：目前不處理（macOS 可在之後以 IOPMAssertion 實作）。"""

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass


class _WindowsPowerRequest:
    POWER_REQUEST_CONTEXT_VERSION = 0
    POWER_REQUEST_CONTEXT_SIMPLE_STRING = 0x1
    POWER_REQUEST_SYSTEM_REQUIRED = 1

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class _Detailed(ctypes.Structure):
            _fields_ = [
                ("LocalizedReasonModule", wintypes.HMODULE),
                ("LocalizedReasonId", wintypes.ULONG),
                ("ReasonStringCount", wintypes.ULONG),
                ("ReasonStrings", ctypes.POINTER(wintypes.LPWSTR)),
            ]

        class _Reason(ctypes.Union):
            _fields_ = [("Detailed", _Detailed), ("SimpleReasonString", wintypes.LPWSTR)]

        class REASON_CONTEXT(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("Flags", wintypes.DWORD), ("Reason", _Reason)]

        self._ctypes = ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        k.PowerCreateRequest.argtypes = [ctypes.POINTER(REASON_CONTEXT)]
        k.PowerCreateRequest.restype = wintypes.HANDLE
        k.PowerSetRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k.PowerSetRequest.restype = wintypes.BOOL
        k.PowerClearRequest.argtypes = [wintypes.HANDLE, ctypes.c_int]
        k.PowerClearRequest.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        self._k = k

        self._reason_text = ctypes.create_unicode_buffer(REASON)  # 請求存在期間必須保持有效
        ctx = REASON_CONTEXT()
        ctx.Version = self.POWER_REQUEST_CONTEXT_VERSION
        ctx.Flags = self.POWER_REQUEST_CONTEXT_SIMPLE_STRING
        ctx.Reason.SimpleReasonString = ctypes.cast(self._reason_text, wintypes.LPWSTR)
        handle = k.PowerCreateRequest(ctypes.byref(ctx))
        invalid = wintypes.HANDLE(-1).value
        if not handle or handle == invalid:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        self._handle = handle

    def enable(self) -> None:
        if not self._k.PowerSetRequest(self._handle, self.POWER_REQUEST_SYSTEM_REQUIRED):
            raise self._ctypes.WinError(self._ctypes.get_last_error())  # type: ignore[attr-defined]

    def disable(self) -> None:
        if not self._k.PowerClearRequest(self._handle, self.POWER_REQUEST_SYSTEM_REQUIRED):
            raise self._ctypes.WinError(self._ctypes.get_last_error())  # type: ignore[attr-defined]


def _default_backend() -> _Backend:
    if sys.platform == "win32":
        return _WindowsPowerRequest()
    return _NoopBackend()


class KeepAwake:
    def __init__(self, backend: _Backend | None = None) -> None:
        self._backend = backend
        self._count = 0
        self._lock = threading.Lock()

    def _get_backend(self) -> _Backend:
        if self._backend is None:  # 第一次需要時才建立（匯入模組不呼叫系統 API）
            self._backend = _default_backend()
        return self._backend

    @property
    def active(self) -> bool:
        with self._lock:
            return self._count > 0

    def acquire(self) -> None:
        with self._lock:
            self._count += 1
            if self._count == 1:
                self._call("enable")

    def release(self) -> None:
        with self._lock:
            if self._count == 0:
                return
            self._count -= 1
            if self._count == 0:
                self._call("disable")

    def _call(self, action: str) -> None:
        try:
            getattr(self._get_backend(), action)()
            _log(f"[power] system-required request {'on' if action == 'enable' else 'off'}")
        except OSError as e:  # 防止睡眠失敗不應讓工作失敗；記錄下來方便排查
            _log(f"[power] could not {action} system-required request: {e}")

    @contextmanager
    def hold(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


def _log(line: str) -> None:
    # Electron 當機時 stdout 管線已斷開：輸出失敗不能影響工作（同 app/main.py 的 stdin 監看）
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        pass


KEEP_AWAKE = KeepAwake()
