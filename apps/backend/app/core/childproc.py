"""啟動「必須跟著後端一起結束」的子程序（例如 llama-server）。

後端正常結束時會自己關掉子程序；這裡處理的是後端**異常結束**（當機、被工作管理員結束）的情況，
避免留下佔用好幾 GB 記憶體的孤兒程序：

- Windows：把子程序放進一個設定了 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 的 Job Object。
  Job handle 只有後端持有；後端一結束（不論原因）handle 被系統關閉，Job 內的程序就被終止。
- Linux：prctl(PR_SET_PDEATHSIG, SIGKILL)。注意它綁的是「建立子程序的執行緒」，
  所以子程序必須由會一直存活到子程序結束的執行緒建立（本專案在工作執行緒內啟動並在同一執行緒內關閉，符合）。
- macOS：沒有對應的機制；正常結束時由後端關閉（Phase 11 打包時再評估）。

ctypes 原則同 app/core/procmem.py：私有 WinDLL／CDLL、宣告 argtypes/restype、檢查回傳值、失敗就 raise。
"""
from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Sequence
from typing import Any

_job_lock = threading.Lock()
_job_handle: int | None = None


def _windows_job() -> int:
    """建立（一次）設定為「handle 關閉即終止所有程序」的 Job Object。"""
    global _job_handle
    with _job_lock:
        if _job_handle is not None:
            return _job_handle
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),  # ULONG_PTR
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k.SetInformationJobObject.restype = wintypes.BOOL

        job = k.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        job_object_extended_limit_information = 9
        if not k.SetInformationJobObject(job, job_object_extended_limit_information, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        _job_handle = job  # 刻意不關閉：後端結束時由系統關閉，觸發 KILL_ON_JOB_CLOSE
        return job


def _assign_to_job(proc: subprocess.Popen[Any]) -> None:
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    handle = int(proc._handle)  # type: ignore[attr-defined]  # Popen 的程序 handle（Windows）
    if not k.AssignProcessToJobObject(_windows_job(), handle):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]


def _linux_pdeathsig_hook():  # type: ignore[no-untyped-def]
    """在父程序準備好 prctl 函式，子程序（fork 之後、exec 之前）只做一次呼叫，不 import 任何東西（避免 fork 後的鎖死）。"""
    import ctypes
    import signal

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    sigkill = int(signal.SIGKILL)

    def hook() -> None:  # pragma: no cover - runs in the child
        if prctl(1, sigkill, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            raise OSError("prctl(PR_SET_PDEATHSIG) failed")

    return hook


def spawn_tied(args: Sequence[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """像 subprocess.Popen(args, **kwargs)，但子程序會隨後端結束。

    Windows 上若加入 Job 失敗，終止子程序並 raise（不留下不受控的程序）。
    """
    if sys.platform.startswith("linux"):
        kwargs.setdefault("preexec_fn", _linux_pdeathsig_hook())
    proc = subprocess.Popen(list(args), **kwargs)  # noqa: S603 - fixed executable, argument list (no shell)
    if sys.platform == "win32":
        try:
            _assign_to_job(proc)
        except OSError:
            proc.kill()
            proc.wait(10)
            raise
    return proc
