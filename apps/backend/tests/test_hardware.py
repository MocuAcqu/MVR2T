"""Phase 10: hardware detection, runtime selection (GPU / CPU / memory downgrade), GPU fallback, CUDA runtime download."""
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path

import pytest

from app.core import hardware as hw
from app.core import runtime_select as rs
from app.core.hardware import Gpu, HardwareProfile
from app.engines.llm.gguf import block_count, kv_bytes_per_token, read_metadata
from app.engines.llm.server import LlmError
from app.models import runtime as rt
from app.services.summary import FallbackLlm

GiB = 1024**3

NVIDIA_SMI = "NVIDIA GeForce RTX 3060, 12288, 11000, 560.94\n"


# --------------------------------------------------------------------------- GGUF


def gguf_bytes(meta: dict[str, object]) -> bytes:
    """A tiny GGUF v3 file with only metadata (and a tokenizer-like string array that must be skipped)."""

    def s(x: str) -> bytes:
        b = x.encode()
        return struct.pack("<Q", len(b)) + b

    kv = b""
    items = list(meta.items()) + [("tokenizer.ggml.tokens", ["a", "bb", "ccc"]), ("tokenizer.ggml.scores", [0.5, 1.5])]
    for k, v in items:
        kv += s(k)
        if isinstance(v, str):
            kv += struct.pack("<I", 8) + s(v)
        elif isinstance(v, int):
            kv += struct.pack("<I", 4) + struct.pack("<I", v)
        elif isinstance(v, list) and v and isinstance(v[0], str):
            kv += struct.pack("<I", 9) + struct.pack("<I", 8) + struct.pack("<Q", len(v)) + b"".join(s(x) for x in v)
        elif isinstance(v, list):
            kv += struct.pack("<I", 9) + struct.pack("<I", 6) + struct.pack("<Q", len(v)) + b"".join(struct.pack("<f", x) for x in v)
    return b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", len(items)) + kv


@pytest.fixture()
def model(tmp_path) -> Path:
    p = tmp_path / "m.gguf"
    meta = {
        "general.architecture": "qwen35",
        "qwen35.block_count": 32,
        "qwen35.attention.head_count_kv": 4,
        "qwen35.attention.key_length": 256,
        "qwen35.full_attention_interval": 4,
    }
    p.write_bytes(gguf_bytes(meta))
    return p


def test_gguf_metadata_layers_and_kv_size(model):
    assert read_metadata(model, {"general.architecture"}) == {"general.architecture": "qwen35"}
    assert block_count(model) == 32
    assert kv_bytes_per_token(model) == 8 * 4 * 512 * 2  # 8 full-attention layers x 4 kv heads x (256+256) x f16
    assert block_count(model.parent / "missing.gguf") is None
    (model.parent / "bad.gguf").write_bytes(b"NOPE")
    assert block_count(model.parent / "bad.gguf") is None


# --------------------------------------------------------------------------- detection


def test_parsers():
    g = hw.parse_nvidia_smi(NVIDIA_SMI)[0]
    assert (g.vendor, g.name, g.vram_total, g.vram_free, g.driver) == ("NVIDIA", "NVIDIA GeForce RTX 3060", 12 * GiB, 11000 * 1024**2, "560.94")
    assert hw.parse_meminfo("MemTotal:  16000000 kB\nMemFree: 1000 kB\nMemAvailable:  8000000 kB\n") == (16000000 * 1024, 8000000 * 1024)
    vm = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100.\nPages inactive: 50.\nPages active: 999.\n"
    assert hw._mac_available(vm, 10**12) == 150 * 16384
    assert hw._vendor("Intel(R) UHD Graphics 620") == "Intel" and hw._vendor("AMD Radeon(TM) Graphics") == "AMD"


def test_windows_11_name_and_virtual_display_adapters():
    assert hw.windows_name("10", "10.0.26200") == "Windows 11"
    assert hw.windows_name("10", "10.0.19045") == "Windows 10"
    assert hw.windows_name("10", "?") == "Windows 10"
    for name in ("DeskIn Virtual Display Adapter", "Microsoft Basic Display Adapter", "Parsec Virtual Display Adapter",
                 "Microsoft Remote Display Adapter", "spacedesk Graphics Adapter"):
        assert hw.is_virtual_adapter(name), name
    for name in ("Intel(R) Iris(R) Xe Graphics", "NVIDIA GeForce RTX 3060 Laptop GPU", "AMD Radeon(TM) Graphics"):
        assert not hw.is_virtual_adapter(name), name


def test_cuda_and_metal_assessment():
    nv = hw.parse_nvidia_smi(NVIDIA_SMI)
    assert hw.assess_cuda("win32", "x64", nv)[0]
    ok, why = hw.assess_cuda("win32", "x64", [Gpu("Intel", "Intel(R) Iris(R) Xe Graphics", 128 * 1024**2)])
    assert not ok and "NVIDIA" in why
    ok, why = hw.assess_cuda("win32", "x64", [Gpu("NVIDIA", "GTX 1060", None, None, None)])
    assert not ok and "nvidia-smi" in why
    ok, why = hw.assess_cuda("win32", "x64", [Gpu("NVIDIA", "GTX 1060", 6 * GiB, 5 * GiB, "472.12")])
    assert not ok and "太舊" in why
    assert not hw.assess_cuda("darwin", "arm64", nv)[0]
    assert hw.assess_metal("darwin", "arm64")[0] and not hw.assess_metal("darwin", "x64")[0] and not hw.assess_metal("win32", "x64")[0]


def test_detect_uses_nvidia_smi_and_never_fails(monkeypatch):
    if hw.sys.platform != "linux":
        pytest.skip("linux detection path")
    p = hw.detect(refresh=True, runner=lambda cmd, t: NVIDIA_SMI if cmd[0] == "nvidia-smi" else None)
    assert p.cuda_available and p.nvidia and p.nvidia.vram_total == 12 * GiB and p.ram_total > 0
    p = hw.detect(refresh=True, runner=lambda cmd, t: None)  # nvidia-smi missing
    assert not p.cuda_available and p.gpus == []
    hw.detect(refresh=True)  # restore the real cache


# --------------------------------------------------------------------------- runtime selection


def profile(ram_available=10 * GiB, gpus=(), cuda=False, metal=False, plat="win32", arch="x64") -> HardwareProfile:
    return HardwareProfile(plat, "Test OS", arch, "CPU", 8, 16 * GiB, ram_available, list(gpus), cuda, "", metal, "")


@pytest.fixture()
def exes(tmp_path, monkeypatch):
    cpu = tmp_path / "cpu" / "llama-server"
    cuda = tmp_path / "cuda" / "llama-server"
    for p in (cpu, cuda):
        p.parent.mkdir()
        p.write_bytes(b"x")
    monkeypatch.setenv("MVR2T_LLAMA_SERVER", str(cpu))
    monkeypatch.setenv("MVR2T_LLAMA_SERVER_CUDA", str(cuda))
    monkeypatch.setattr(rs, "variant_platform", lambda v=rt.CPU, release=None: "win-cuda-12.4-x64" if v == rt.CUDA else "win-cpu-x64")
    return cpu, cuda


MODEL_BYTES = 2_700 * 1024**2


def make_plan(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    return rs.plan_llm(*args, model_bytes=MODEL_BYTES, **kwargs)


def big_model(tmp_path) -> Path:
    """GGUF metadata only; the size is passed as model_bytes. (Not a sparse 2.7 GB file: on Windows/NTFS truncate()
    really allocates the space, see test_transcribe_service.data_dir.)"""
    p = tmp_path / "big.gguf"
    p.write_bytes(gguf_bytes({"general.architecture": "qwen35", "qwen35.block_count": 32, "qwen35.attention.head_count_kv": 4,
                              "qwen35.attention.key_length": 256, "qwen35.full_attention_interval": 4}))
    return p


def test_cpu_when_there_is_no_usable_gpu(tmp_path, exes):
    m = big_model(tmp_path)
    plan = make_plan(profile(gpus=[Gpu("Intel", "Intel UHD", 128 * 1024**2)]), tmp_path, m)
    assert (plan.device, plan.n_gpu_layers, plan.ctx) == ("cpu", 0, 8192) and "Intel" in plan.reason
    assert plan.executable == str(exes[0])


def test_memory_downgrade_and_clear_error(tmp_path, exes):
    m = big_model(tmp_path)
    need_8k = 2_700 * 1024**2 + 32768 * 8192 + rs.OVERHEAD
    plan = make_plan(profile(ram_available=need_8k - 10 * 1024**2), tmp_path, m)
    assert plan.ctx == 4096 and "較短的 context" in plan.warnings[0]
    plan = make_plan(profile(ram_available=int(2.5 * GiB)), tmp_path, m)
    assert plan.ctx == 4096 and "偏少" in plan.warnings[0]
    with pytest.raises(rs.InsufficientMemory, match="可用記憶體不足"):
        make_plan(profile(ram_available=int(1.5 * GiB)), tmp_path, m)
    report = make_plan(profile(ram_available=int(1.5 * GiB)), tmp_path, m, check_memory=False)
    assert "可用記憶體不足" in report.warnings[0]  # shown on the "this computer" card instead of raising


def nvidia_profile(driver="560.94", **kw) -> HardwareProfile:
    return profile(gpus=[Gpu("NVIDIA", "RTX 3060", 12 * GiB, 11 * GiB, driver)], cuda=True, **kw)


def test_cuda_full_partial_or_cpu_depending_on_free_vram(tmp_path, exes):
    m = big_model(tmp_path)
    full = make_plan(nvidia_profile(), tmp_path, m, vram_free=6 * GiB)
    assert (full.device, full.n_gpu_layers, full.executable, full.cpu_executable) == ("cuda", 999, str(exes[1]), str(exes[0]))
    part = make_plan(nvidia_profile(), tmp_path, m, vram_free=2 * GiB)
    assert part.device == "cuda" and 8 <= part.n_gpu_layers < 32 and "層" in part.reason
    low = make_plan(nvidia_profile(), tmp_path, m, vram_free=600 * 1024**2)
    assert low.device == "cpu" and "VRAM" in low.reason


def test_cuda_needs_a_recent_driver_and_the_gpu_build(tmp_path, exes, monkeypatch):
    m = big_model(tmp_path)
    old = make_plan(nvidia_profile(driver="510.10"), tmp_path, m, vram_free=6 * GiB)
    assert old.device == "cpu" and "驅動程式" in old.reason
    monkeypatch.delenv("MVR2T_LLAMA_SERVER_CUDA")
    missing = make_plan(nvidia_profile(), tmp_path, m, vram_free=6 * GiB)
    assert missing.device == "cpu" and "摘要 GPU 加速" in missing.reason


def test_metal_on_apple_silicon(tmp_path, exes):
    plan = make_plan(profile(plat="darwin", arch="arm64", metal=True), tmp_path, big_model(tmp_path))
    assert (plan.device, plan.n_gpu_layers) == ("metal", 999)


def test_asr_stays_on_cpu_and_warns_when_memory_is_low():
    assert rs.plan_asr(nvidia_profile()).device == "cpu"
    assert "3 GB" in rs.plan_asr(profile(ram_available=2 * GiB)).warnings[0]
    assert rs.plan_asr(profile()).warnings == []


# --------------------------------------------------------------------------- GPU -> CPU fallback


class FakeServer:
    def __init__(self, opts, fail: bool) -> None:  # noqa: ANN001
        self.opts, self.fail, self.killed = opts, fail, False

    def __enter__(self):  # noqa: ANN204
        if self.fail:
            raise LlmError("記憶體不足，無法載入摘要模型。")
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def chat(self, *a, **k):  # noqa: ANN002, ANN003
        return "ok"

    def kill(self) -> None:
        self.killed = True


def test_gpu_start_failure_falls_back_to_cpu(tmp_path):
    made = []

    def make(opts):  # noqa: ANN001
        s = FakeServer(opts, fail="cuda" in str(opts.executable))
        made.append(s)
        return s

    plan = rs.LlmPlan("cuda", "/x/cuda/llama-server", 999, 8192, "GPU", [], "/x/cpu/llama-server")
    with FallbackLlm(plan, tmp_path / "m.gguf", 0, make) as llm:
        assert llm.chat() == "ok"
    assert llm.device == "cpu" and "已改用 CPU" in llm.note
    assert [m.opts.extra_args for m in made] == [("--n-gpu-layers", "999"), ("--n-gpu-layers", "0")]

    cpu_plan = rs.LlmPlan("cpu", "/x/cuda/llama-server", 0, 4096, "CPU", ["w"], "/x/cuda/llama-server")
    with pytest.raises(LlmError):  # already on CPU: nothing to fall back to
        with FallbackLlm(cpu_plan, tmp_path / "m.gguf", 0, make):
            pass


# --------------------------------------------------------------------------- CUDA runtime download (main + cudart)


def test_cuda_runtime_installs_with_its_cuda_libraries_next_to_the_exe(tmp_path, monkeypatch):
    from tests.test_model_manager import Server

    def zip_bytes(files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k, v in files.items():
                z.writestr(k, v)
        return buf.getvalue()

    import hashlib

    main = zip_bytes({f"bin/{rt.exe_name()}": b"server", "bin/ggml-cuda.dll": b"ggml"})
    cudart = zip_bytes({"cudart64_12.dll": b"rt", "cublas64_12.dll": b"blas"})
    server = Server()
    try:
        server.files["/b1/main.zip"] = main
        server.files["/b1/cudart.zip"] = cudart
        plat = "win-cuda-12.4-x64"

        class Rel(rt.LlamaCppRelease):
            def url(self, asset):  # noqa: ANN001, ANN201
                return f"{server.url}/b1/{asset.filename}"

        release = Rel(tag="b1", commit="c", assets=(
            rt.RuntimeAsset("win-cpu-x64", "cpu.zip", 1, "0" * 64),
            rt.RuntimeAsset(plat, "main.zip", len(main), hashlib.sha256(main).hexdigest()),
            rt.RuntimeAsset(f"{plat}:cudart", "cudart.zip", len(cudart), hashlib.sha256(cudart).hexdigest()),
        ))
        monkeypatch.delenv("MVR2T_LLAMA_SERVER_CUDA", raising=False)
        assert rt.runtime_size(release, plat) == len(main) + len(cudart)
        got: list[int] = []
        exe = rt.download_runtime(tmp_path, release, on_progress=lambda s: None, on_bytes=got.append, plat=plat)
        assert exe.read_bytes() == b"server" and sum(got) == len(main) + len(cudart)
        assert (exe.parent / "cudart64_12.dll").read_bytes() == b"rt"
        assert rt.find_llama_server(tmp_path, release, plat) == exe
        assert rt.find_llama_server(tmp_path, release, "win-cpu-x64") is None  # the CPU build is separate
        assert rt.cuda_version(plat) == (12, 4)
    finally:
        server.httpd.shutdown()
