"""Runtime Selector（PROJECT_SPEC §5.4、§6.4、Phase 10）：依硬體決定 AI 工作用哪個裝置、多少 context。

使用者決定（2026-11-14）：摘要（llama.cpp）可以用 GPU；語音辨識（PyTorch）先維持 CPU。

摘要：
- NVIDIA：偵測到 CUDA 可用、驅動版本符合、**而且** CUDA 版 llama.cpp 已安裝 → 用 GPU。
  可用 VRAM 放得下整個模型＋KV cache → 全部層放 GPU；放不下 → 只放一部分層（其餘在 CPU）；
  能放的層太少（< 25%）→ 直接用 CPU。
- Apple Silicon：macOS 版 llama.cpp 內建 Metal，統一記憶體 → 全部層放 GPU。
- 其他（含 Intel／AMD 內顯，第一版不承諾加速，§6.2）→ CPU。
- 記憶體不足的降級：可用記憶體不夠預設 context（8192）→ 改用 4096（長逐字稿會分成較多段）；
  連最低需求都不夠 → 不嘗試載入，回報清楚的錯誤（§5.4：不可直接崩潰）。
- GPU 啟動失敗（例如 VRAM 被其他程式佔用）→ 由 services/summary 的 FallbackLlm 自動改用 CPU 再試一次。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.hardware import HardwareProfile, driver_tuple, nvidia_free_vram
from app.engines.llm.gguf import block_count, kv_bytes_per_token
from app.models.runtime import CPU, CUDA, cuda_version, find_llama_server, variant_platform

Device = Literal["cpu", "cuda", "metal"]

GiB = 1024**3
MiB = 1024**2
#: llama-server 除了模型與 KV cache 之外的工作記憶體（計算緩衝、程式本身）
OVERHEAD = 600 * MiB
#: GPU 上另外保留給驅動與桌面顯示
VRAM_RESERVE = 500 * MiB
#: KV cache 大小讀不到時的保守估計（每個 token）
KV_FALLBACK = 150 * 1024
MIN_CTX = 4096
#: 可用記憶體低於這個值就不嘗試載入摘要模型（一定會失敗或讓電腦卡住）
HARD_MIN_RAM = 2 * GiB
#: 放到 GPU 的層數低於這個比例就不值得（CPU↔GPU 來回傳輸反而慢）
MIN_GPU_LAYER_RATIO = 0.25
#: CUDA 主版本 → 需要的最低驅動（Windows）
MIN_DRIVER_FOR_CUDA = {12: (527, 41), 13: (580, 0)}


class InsufficientMemory(Exception):
    """給使用者看的錯誤（繁體中文）。"""


@dataclass
class LlmPlan:
    device: Device
    executable: str | None
    n_gpu_layers: int  # 0 = 全部在 CPU；999 = 全部放 GPU
    ctx: int
    reason: str
    warnings: list[str] = field(default_factory=list)
    #: GPU 失敗時改用的 CPU 版執行檔（device = cpu 時與 executable 相同）
    cpu_executable: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _needed(model_bytes: int, kv_per_token: int, ctx: int) -> int:
    return model_bytes + kv_per_token * ctx + OVERHEAD


def cuda_build_ok(profile: HardwareProfile, plat: str | None) -> tuple[bool, str]:
    """CUDA 版 llama.cpp 能不能在這張卡、這個驅動上跑。"""
    if not profile.cuda_available:
        return False, profile.cuda_reason
    if plat is None:
        return False, "這個版本還沒有提供 GPU 版的 llama.cpp。"
    ver = cuda_version(plat)
    nv = profile.nvidia
    need = MIN_DRIVER_FOR_CUDA.get(ver[0], (999, 0)) if ver else (999, 0)
    have = driver_tuple(nv.driver if nv else None)
    if have is None or have < need:
        return False, f"GPU 版 llama.cpp（CUDA {ver[0]}.{ver[1] if ver else ''}）需要 NVIDIA 驅動程式 {need[0]}.{need[1]} 以上。"
    return True, ""


def plan_llm(
    profile: HardwareProfile,
    runtime_root: Path,
    model_path: Path,
    ctx: int = 8192,
    vram_free: int | None = None,
    check_memory: bool = True,
    model_bytes: int | None = None,
    force_cpu: bool = False,
) -> LlmPlan:
    """選擇摘要的執行方式。check_memory=False 時只回報建議、不丟出記憶體不足（給「這台電腦」頁面顯示用）。"""
    cpu_exe = find_llama_server(runtime_root, plat=variant_platform(CPU))
    if model_bytes is None:  # 測試可直接給大小（不必建立數 GB 的檔案）
        model_bytes = model_path.stat().st_size if model_path.is_file() else 2_800 * MiB
    kv = (kv_bytes_per_token(model_path) if model_path.is_file() else None) or KV_FALLBACK
    layers = (block_count(model_path) if model_path.is_file() else None) or 32
    ctxs = [c for c in (ctx, MIN_CTX) if c >= MIN_CTX] if ctx > MIN_CTX else [max(ctx, 512)]
    warnings: list[str] = []

    if force_cpu:  # 設定頁「推論裝置：一律使用 CPU」
        c = _fit_ctx(profile, model_bytes, kv, ctxs, warnings, check_memory)
        exe = str(cpu_exe) if cpu_exe else None
        return LlmPlan("cpu", exe, 0, c, "CPU（設定為一律使用 CPU）", warnings, exe)

    # --- GPU：NVIDIA CUDA ---
    cuda_plat = variant_platform(CUDA)
    ok, why_not = cuda_build_ok(profile, cuda_plat)
    cuda_exe = find_llama_server(runtime_root, plat=cuda_plat) if ok and cuda_plat else None
    if ok and cuda_exe is None:
        why_not = "可以用 NVIDIA GPU 加速：請到「模型管理」下載「摘要 GPU 加速」。"
    if ok and cuda_exe is not None:
        vram = vram_free if vram_free is not None else (nvidia_free_vram() or 0)
        for c in ctxs:
            gpu_need = model_bytes + kv * c + VRAM_RESERVE
            if vram >= gpu_need:
                return LlmPlan("cuda", str(cuda_exe), 999, c, f"NVIDIA GPU（{profile.nvidia.name if profile.nvidia else ''}，模型全部放在 GPU）", warnings, str(cpu_exe) if cpu_exe else None)
        c = ctxs[0]
        fit = int(layers * max(0, vram - kv * c - VRAM_RESERVE) / max(1, model_bytes))
        if fit >= layers * MIN_GPU_LAYER_RATIO:
            return LlmPlan(
                "cuda", str(cuda_exe), fit, c,
                f"NVIDIA GPU（VRAM 可用 {vram / GiB:.1f} GB，放 {fit}／{layers} 層到 GPU，其餘用 CPU）",
                warnings, str(cpu_exe) if cpu_exe else None,
            )
        why_not = f"NVIDIA GPU 可用的 VRAM 太少（{vram / GiB:.1f} GB），改用 CPU。"

    # --- GPU：Apple Silicon Metal（macOS 版 llama.cpp 內建）---
    if profile.metal_available and cpu_exe is not None:
        c = _fit_ctx(profile, model_bytes, kv, ctxs, warnings, check_memory)
        return LlmPlan("metal", str(cpu_exe), 999, c, "Apple Silicon GPU（Metal，統一記憶體）", warnings, str(cpu_exe))

    # --- CPU ---
    c = _fit_ctx(profile, model_bytes, kv, ctxs, warnings, check_memory)
    reason = "CPU"
    if why_not and profile.cuda_available:
        reason = f"CPU（{why_not}）"
    elif any(g.vendor in ("Intel", "AMD") for g in profile.gpus) and not profile.metal_available:
        reason = "CPU（目前版本尚不支援 Intel／AMD 顯示卡加速）"
    return LlmPlan("cpu", str(cpu_exe) if cpu_exe else None, 0, c, reason, warnings, str(cpu_exe) if cpu_exe else None)


def _fit_ctx(profile: HardwareProfile, model_bytes: int, kv: int, ctxs: list[int], warnings: list[str], check: bool) -> int:
    """記憶體不足的降級：context 由大到小，第一個放得下的；都放不下則錯誤（或只警告）。"""
    avail = profile.ram_available
    if avail <= 0:  # 讀不到記憶體資訊：照預設
        return ctxs[0]
    for i, c in enumerate(ctxs):
        if avail >= _needed(model_bytes, kv, c):
            if i > 0:
                warnings.append(
                    f"可用記憶體較少（{avail / GiB:.1f} GB），改用較短的 context（{c}）；長逐字稿會分成較多段，時間會稍長。"
                )
            return c
    need = _needed(model_bytes, kv, ctxs[-1])
    if avail < HARD_MIN_RAM:
        msg = f"可用記憶體不足：產生摘要約需 {need / GiB:.1f} GB，目前只有 {avail / GiB:.1f} GB。請關閉其他程式（例如瀏覽器分頁）後再試一次。"
        if check:
            raise InsufficientMemory(msg)
        warnings.append(msg)
        return ctxs[-1]
    # 模型以 mmap 載入，記憶體稍微不夠時仍能執行（作業系統會換頁），只是比較慢
    warnings.append(f"可用記憶體偏少（{avail / GiB:.1f} GB，建議 {need / GiB:.1f} GB 以上），摘要可能會比較慢；建議先關閉其他程式。")
    return ctxs[-1]


def llm_options(cfg: Any) -> dict[str, Any]:
    """設定頁的選擇 → plan_llm 的參數（省記憶體：context 4096；一律 CPU：不用 GPU）。"""
    from app.core.user_settings import load

    us = load(cfg.data_dir)
    return {"ctx": MIN_CTX if us.memory == "low" else cfg.llm_ctx, "force_cpu": us.device == "cpu"}


@dataclass
class AsrPlan:
    device: Device
    reason: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: 語音辨識（ASR＋對齊，float32、依序載入）實測尖峰約 3 GB
ASR_NEEDED = 3 * GiB


def plan_asr(profile: HardwareProfile) -> AsrPlan:
    """語音辨識：使用者決定先用 CPU（PyTorch 的 CUDA 版約 2.5 GB，打包時再評估）。只在記憶體偏少時提醒。"""
    reason = "CPU"
    if profile.cuda_available or profile.metal_available:
        reason = "CPU（語音辨識的 GPU 加速將在之後的版本評估）"
    warnings = []
    if 0 < profile.ram_available < ASR_NEEDED:
        warnings.append(
            f"可用記憶體只有 {profile.ram_available / GiB:.1f} GB（語音辨識約需 3 GB），可能會很慢或失敗；建議先關閉其他程式。"
        )
    return AsrPlan("cpu", reason, warnings)
