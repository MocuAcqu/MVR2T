"""目前程序的記憶體用量（跨平台，不需額外套件）。測試與 scripts/benchmark_asr.py 共用。

Windows 的寫法沿用 Claude Code 在本機驗證過的版本（9b3a5a8）：
- 一律使用自己的 ctypes.WinDLL 實例並設定 argtypes / restype。64 位元 Windows 上若沒設定 restype，
  GetCurrentProcess() 的特殊 handle（-1）會被截成 32 位元，GetProcessMemoryInfo 失敗，結構維持 0，
  讀數變成「假的 0 MB」（2026-11-09 曾因此讓記憶體測試永遠假通過）。
- 呼叫失敗時 raise WinError，絕不回報假的 0。
- 不使用 ctypes.windll 全域實例，避免改到其他程式碼共用的函式型別。
"""
from __future__ import annotations

import sys


def _windows_counters() -> tuple[float, float]:
    """回傳 (WorkingSetSize, PeakWorkingSetSize)，單位 MB。"""
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    psapi = ctypes.WinDLL("psapi", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]  # never report a fake 0 MB
    return pmc.WorkingSetSize / 1024**2, pmc.PeakWorkingSetSize / 1024**2


def current_rss_mb() -> float | None:
    """目前的常駐記憶體（MB）。Windows：WorkingSetSize；Linux：VmRSS。macOS 無法免套件取得 → None。"""
    if sys.platform == "win32":
        return _windows_counters()[0]
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            return next(int(line.split()[1]) / 1024 for line in f if line.startswith("VmRSS"))
    except (OSError, StopIteration):
        return None


def peak_rss_mb() -> float:
    """程序啟動以來的峰值記憶體（MB）。"""
    if sys.platform == "win32":
        return _windows_counters()[1]
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # 單位：macOS 是 bytes、Linux 是 KB
    return peak / 1024**2 if sys.platform == "darwin" else peak / 1024
