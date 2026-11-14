"""硬體偵測（PROJECT_SPEC §6、Phase 10）：CPU、記憶體、GPU、VRAM、CUDA、Metal。

原則（§6.1）：不能只因為「有 GPU」就認定可以用 GPU。這裡只回報事實，能不能用由 runtime_select 判斷
（還要看 llama.cpp 的 GPU 版本是否已安裝、驅動版本、VRAM 是否夠）。

偵測方式（都不需要額外套件，也不連網）：
- Windows：記憶體 GlobalMemoryStatusEx；CPU 名稱與顯示卡（名稱、VRAM）讀登錄檔
  （顯示卡類別 {4d36e968-…} 的 DriverDesc、HardwareInformation.qwMemorySize）；NVIDIA 另外用 nvidia-smi 取得驅動版本與可用 VRAM。
- macOS：sysctl（CPU、記憶體）、vm_stat（可用記憶體）；Apple Silicon 視為 Metal 可用（統一記憶體）。
- Linux（開發與沙盒）：/proc/cpuinfo、/proc/meminfo、nvidia-smi。
GPU 資訊不會變，偵測一次後快取；可用記憶體每次重新讀。
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

#: llama.cpp 的 CUDA 12.4 版本需要的最低 NVIDIA 驅動（CUDA 12.x minor version compatibility：Windows 527.41、Linux 525.60）
MIN_NVIDIA_DRIVER = {"win32": (527, 41), "linux": (525, 60)}

Runner = Callable[[list[str], float], str | None]


def run(cmd: list[str], timeout: float = 5.0) -> str | None:
    """執行外部指令並回傳輸出；失敗、找不到或逾時回傳 None（偵測失敗不能讓程式出錯）。"""
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=flags, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


@dataclass
class Gpu:
    vendor: str  # NVIDIA / AMD / Intel / Apple / 其他
    name: str
    vram_total: int | None = None  # bytes；Apple Silicon 為 None（統一記憶體）
    vram_free: int | None = None  # 只有 NVIDIA（nvidia-smi）有
    driver: str | None = None


@dataclass
class HardwareProfile:
    platform: str  # win32 / darwin / linux
    os_name: str
    arch: str  # x64 / arm64
    cpu_name: str
    cpu_threads: int
    ram_total: int
    ram_available: int
    gpus: list[Gpu] = field(default_factory=list)
    cuda_available: bool = False
    cuda_reason: str = ""
    metal_available: bool = False
    metal_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def nvidia(self) -> Gpu | None:
        return next((g for g in self.gpus if g.vendor == "NVIDIA"), None)


def _vendor(name: str) -> str:
    low = name.lower()
    for key, vendor in (("nvidia", "NVIDIA"), ("geforce", "NVIDIA"), ("quadro", "NVIDIA"), ("radeon", "AMD"), ("amd", "AMD"),
                        ("intel", "Intel"), ("apple", "Apple")):
        if key in low:
            return vendor
    return "其他"


def _arch() -> str:
    m = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(m, m)


# --------------------------------------------------------------------------- 記憶體


def memory() -> tuple[int, int]:
    """(總記憶體, 可用記憶體) bytes；讀不到時 (0, 0)。"""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
            k32.GlobalMemoryStatusEx.restype = wintypes.BOOL
            if k32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys), int(stat.ullAvailPhys)
            return 0, 0
        if sys.platform == "darwin":
            total = int((run(["sysctl", "-n", "hw.memsize"]) or "0").strip() or 0)
            return total, _mac_available(run(["vm_stat"]) or "", total)
        return parse_meminfo(open("/proc/meminfo", encoding="ascii").read())  # noqa: SIM115
    except (OSError, ValueError):
        return 0, 0


def parse_meminfo(text: str) -> tuple[int, int]:
    vals = {m.group(1): int(m.group(2)) * 1024 for m in re.finditer(r"^(\w+):\s+(\d+) kB", text, re.M)}
    return vals.get("MemTotal", 0), vals.get("MemAvailable", vals.get("MemFree", 0))


def _mac_available(vm_stat: str, total: int) -> int:
    page = int(m.group(1)) if (m := re.search(r"page size of (\d+) bytes", vm_stat)) else 16384
    pages = {k: int(v) for k, v in re.findall(r"Pages (free|inactive|speculative|purgeable):\s+(\d+)\.", vm_stat)}
    avail = sum(pages.values()) * page
    return min(avail, total) if total else avail


# --------------------------------------------------------------------------- CPU


def cpu_name(runner: Runner = run) -> str:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        if sys.platform == "darwin":
            return (runner(["sysctl", "-n", "machdep.cpu.brand_string"], 5) or "").strip() or platform.processor()
        text = open("/proc/cpuinfo", encoding="utf-8", errors="replace").read()  # noqa: SIM115
        if m := re.search(r"^model name\s*:\s*(.+)$", text, re.M):
            return m.group(1).strip()
    except OSError:
        pass
    return platform.processor() or "未知"


# --------------------------------------------------------------------------- GPU


def parse_nvidia_smi(text: str) -> list[Gpu]:
    """nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader,nounits（MiB）"""
    gpus = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            total, free = int(float(parts[1])) * 1024**2, int(float(parts[2])) * 1024**2
        except ValueError:
            total = free = None  # type: ignore[assignment]
        gpus.append(Gpu("NVIDIA", parts[0], total, free, parts[3]))
    return gpus


def nvidia_gpus(runner: Runner = run) -> list[Gpu]:
    out = runner(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"], 8)
    return parse_nvidia_smi(out) if out else []


def windows_display_adapters() -> list[Gpu]:
    """登錄檔的顯示卡清單（名稱、專用 VRAM）。不用 WMI：AdapterRAM 是 32 位元，超過 4 GB 會錯。"""
    gpus: list[Gpu] = []
    try:
        import winreg

        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, sub) as k:
                        name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                        vram: int | None = None
                        for value in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                raw = winreg.QueryValueEx(k, value)[0]
                                vram = int.from_bytes(raw, "little") if isinstance(raw, bytes) else int(raw)
                                break
                            except OSError:
                                continue
                        try:
                            driver = str(winreg.QueryValueEx(k, "DriverVersion")[0])
                        except OSError:
                            driver = None
                except OSError:
                    continue
                if "basic display" in name.lower() or "remote" in name.lower():
                    continue  # 「Microsoft 基本顯示介面卡」、遠端桌面
                gpus.append(Gpu(_vendor(name), name, vram or None, None, driver))
    except OSError:
        pass
    return gpus


def mac_gpus(runner: Runner = run) -> list[Gpu]:
    out = runner(["system_profiler", "SPDisplaysDataType"], 10) or ""
    names = re.findall(r"Chipset Model:\s*(.+)", out)
    return [Gpu(_vendor(n), n.strip()) for n in names]


def driver_tuple(version: str | None) -> tuple[int, int] | None:
    if not version:
        return None
    m = re.match(r"(\d+)\.(\d+)", version)
    return (int(m.group(1)), int(m.group(2))) if m else None


def merge_gpus(adapters: list[Gpu], nvidia: list[Gpu]) -> list[Gpu]:
    """登錄檔的清單＋nvidia-smi 的詳細資料（NVIDIA 以 nvidia-smi 為準）。"""
    others = [g for g in adapters if g.vendor != "NVIDIA"]
    if nvidia:
        return nvidia + others
    return adapters


def assess_cuda(plat: str, arch: str, gpus: list[Gpu]) -> tuple[bool, str]:
    if plat not in ("win32", "linux") or arch != "x64":
        return False, "這個作業系統不使用 CUDA。"
    nv = next((g for g in gpus if g.vendor == "NVIDIA"), None)
    if nv is None:
        return False, "沒有偵測到 NVIDIA 顯示卡。"
    if nv.driver is None or nv.vram_total is None:
        return False, "偵測到 NVIDIA 顯示卡，但無法執行 nvidia-smi（請安裝或更新 NVIDIA 驅動程式）。"
    need = MIN_NVIDIA_DRIVER.get(plat, (999, 0))
    have = driver_tuple(nv.driver)
    if have is None or have < need:
        return False, f"NVIDIA 驅動程式版本 {nv.driver} 太舊，需要 {need[0]}.{need[1]} 以上（請更新驅動程式）。"
    return True, f"{nv.name}，驅動程式 {nv.driver}"


def assess_metal(plat: str, arch: str) -> tuple[bool, str]:
    if plat != "darwin":
        return False, "Metal 只在 macOS 上使用。"
    if arch != "arm64":
        return False, "Intel Mac 第一版使用 CPU（規格 §6.3）。"
    return True, "Apple Silicon（統一記憶體）"


# --------------------------------------------------------------------------- 整合


_cache: dict[str, Any] = {}
_lock = threading.Lock()


def detect(refresh: bool = False, runner: Runner = run) -> HardwareProfile:
    """硬體資訊。GPU 與 CPU 偵測一次後快取（refresh=True 重新偵測）；可用記憶體每次重新讀。"""
    plat, arch = sys.platform, _arch()
    with _lock:
        if refresh or "static" not in _cache:
            if plat == "win32":
                gpus = merge_gpus(windows_display_adapters(), nvidia_gpus(runner))
            elif plat == "darwin":
                gpus = mac_gpus(runner)
            else:
                gpus = nvidia_gpus(runner)
            cuda = assess_cuda(plat, arch, gpus)
            metal = assess_metal(plat, arch)
            os_name = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}.get(plat, plat)
            release = platform.release() if plat != "darwin" else platform.mac_ver()[0]
            _cache["static"] = {
                "os_name": f"{os_name} {release}".strip(),
                "cpu_name": cpu_name(runner),
                "gpus": gpus,
                "cuda": cuda,
                "metal": metal,
            }
        static = _cache["static"]
    total, available = memory()
    gpus = static["gpus"]  # 可用 VRAM 在選擇執行方式時另外即時查詢（nvidia_free_vram）
    return HardwareProfile(
        platform=plat,
        os_name=static["os_name"],
        arch=arch,
        cpu_name=static["cpu_name"],
        cpu_threads=os.cpu_count() or 1,
        ram_total=total,
        ram_available=available,
        gpus=list(gpus),
        cuda_available=static["cuda"][0],
        cuda_reason=static["cuda"][1],
        metal_available=static["metal"][0],
        metal_reason=static["metal"][1],
    )


def nvidia_free_vram(runner: Runner = run) -> int | None:
    """目前可用的 VRAM（其他程式也會用 GPU，所以每次摘要前重新查）。"""
    gpus = nvidia_gpus(runner)
    return gpus[0].vram_free if gpus else None
