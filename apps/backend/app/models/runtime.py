"""llama.cpp 執行檔（llama-server）的版本固定、下載、驗證與尋找（PROJECT_SPEC §5.3、§7.3、§17）。

使用 llama.cpp 官方 GitHub Release 預先編譯的執行檔，不需要 C++ 編譯器。
- 版本固定在 LLAMA_CPP：release tag 與它對應的 commit；每個平台的壓縮檔都有 SHA-256，下載後驗證。
- 安裝位置：<userData>/runtime/llama/<tag>-<platform>/（規格 §7.3），驗證並解壓縮後寫入 .mvr2t-runtime.json。
- 開發／測試可用環境變數 MVR2T_LLAMA_SERVER 直接指定 llama-server 執行檔（例如自行編譯的版本）。

更新版本：執行 `python -m scripts.resolve_llama_release --commit <commit>`，它會從 GitHub 查出 tag、
各平台壓縮檔的大小與 SHA-256，並印出可直接貼到這裡的設定。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

MARKER = ".mvr2t-runtime.json"


class LlamaRuntimeError(Exception):
    """給使用者看的錯誤（繁體中文）。"""


@dataclass(frozen=True)
class RuntimeAsset:
    platform: str  # 例如 win-cpu-x64
    filename: str
    size: int
    sha256: str


@dataclass(frozen=True)
class LlamaCppRelease:
    tag: str  # 例如 b6xxx；空字串 = 尚未固定（見模組說明）
    commit: str
    assets: tuple[RuntimeAsset, ...] = field(default_factory=tuple)

    def url(self, asset: RuntimeAsset) -> str:
        return f"https://github.com/ggml-org/llama.cpp/releases/download/{self.tag}/{asset.filename}"


# 與沙盒測試使用的原始碼相同的 commit（llama-cpp-python 0.3.36 內附的 llama.cpp，2026-10-01）。
# tag 與 SHA-256 由使用者電腦上的 Claude Code 以 scripts/resolve_llama_release.py 查出（2026-11-10，本機 519e8d7）。
LLAMA_CPP = LlamaCppRelease(
    tag="b11312",
    commit="0c1e57098bba43ac29e6e3b677cdceebdd22334f",
    assets=(
        RuntimeAsset("win-cpu-x64", "llama-b11312-bin-win-cpu-x64.zip", 19265352, "d2d966c23e4d097d70633f9d92e4931245b575be7a5409201d8f352493f0e702"),
        # macOS（.tar.gz）在 Phase 11 打包時以 scripts/resolve_llama_release 補上
    ),
)


def current_platform() -> str | None:
    """這台電腦對應的壓縮檔平台名稱；不支援的平台回傳 None。Phase 10 會加入 GPU 版本。"""
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "win-cpu-x64"
    if sys.platform == "darwin" and machine == "arm64":
        return "macos-arm64"
    return None


def exe_name() -> str:
    return "llama-server.exe" if sys.platform == "win32" else "llama-server"


def install_dir(runtime_root: Path, release: LlamaCppRelease = LLAMA_CPP, plat: str | None = None) -> Path:
    plat = plat or current_platform() or "unknown"
    return runtime_root / "llama" / f"{release.tag or 'unpinned'}-{plat}"


def asset_for(release: LlamaCppRelease, plat: str | None) -> RuntimeAsset | None:
    return next((a for a in release.assets if a.platform == plat), None)


def find_llama_server(runtime_root: Path, release: LlamaCppRelease = LLAMA_CPP) -> Path | None:
    """回傳 llama-server 執行檔路徑；沒有安裝則 None。"""
    override = os.environ.get("MVR2T_LLAMA_SERVER", "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None
    d = install_dir(runtime_root, release)
    try:
        marker = json.loads((d / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if marker.get("tag") != release.tag or not release.tag:
        return None
    exe = next(iter(sorted(d.rglob(exe_name()))), None)
    return exe if exe is not None and exe.is_file() else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def extract_archive(archive: Path, name: str, dest: Path) -> None:
    """解壓縮 .zip（Windows）或 .tar.gz（macOS）。任何會跳出 dest 的路徑或連結都拒絕（zip slip / tar 路徑穿越）。"""
    root = dest.resolve()

    def check(member_name: str) -> None:
        target = (dest / member_name).resolve()
        if not target.is_relative_to(root):
            raise LlamaRuntimeError(f"{name} 內含不安全的路徑：{member_name}")

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                check(info.filename)
            zf.extractall(dest)
    elif name.endswith((".tar.gz", ".tgz")):
        import tarfile

        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            for m in members:
                check(m.name)
                if m.issym() or m.islnk():
                    # 連結目標也必須在資料夾內（macOS 版的 .dylib 會用相對連結）
                    link_base = (dest / m.name).parent if m.issym() else dest
                    if not (link_base / m.linkname).resolve().is_relative_to(root):
                        raise LlamaRuntimeError(f"{name} 內含不安全的連結：{m.name} -> {m.linkname}")
                elif not (m.isfile() or m.isdir()):
                    raise LlamaRuntimeError(f"{name} 內含不支援的檔案類型：{m.name}")
            tf.extractall(dest, members=members)
    else:
        raise LlamaRuntimeError(f"不支援的壓縮格式：{name}")


def download_runtime(
    runtime_root: Path,
    release: LlamaCppRelease = LLAMA_CPP,
    on_progress: Callable[[str], None] = print,
) -> Path:
    """下載、驗證並解壓縮 llama-server；成功回傳執行檔路徑。"""
    override = os.environ.get("MVR2T_LLAMA_SERVER", "").strip()
    if override:
        exe = find_llama_server(runtime_root, release)
        if exe is None:
            raise LlamaRuntimeError(f"MVR2T_LLAMA_SERVER 指定的檔案不存在：{override}")
        on_progress(f"使用 MVR2T_LLAMA_SERVER 指定的 llama-server：{exe}（不下載）")
        return exe
    plat = current_platform()
    asset = asset_for(release, plat)
    if not release.tag or asset is None:
        raise LlamaRuntimeError(
            f"這個平台（{plat or sys.platform}）尚未設定 llama.cpp 執行檔版本。"
            "請先執行 python -m scripts.resolve_llama_release 並把結果填入 app/models/runtime.py。"
        )
    existing = find_llama_server(runtime_root, release)
    if existing is not None:
        on_progress(f"llama.cpp {release.tag}：已安裝，略過（{existing}）")
        return existing

    final = install_dir(runtime_root, release, plat)
    final.parent.mkdir(parents=True, exist_ok=True)
    archive = final.parent / f".{asset.filename}.partial"
    if not (archive.is_file() and archive.stat().st_size == asset.size and _sha256(archive) == asset.sha256):
        on_progress(f"  下載 {asset.filename}（{asset.size / 1024**2:,.1f} MB）…")
        req = urllib.request.Request(release.url(asset), headers={"User-Agent": "MVR2T-model-downloader"})
        with urllib.request.urlopen(req, timeout=60) as res, archive.open("wb") as out:  # noqa: S310 - fixed https URL
            shutil.copyfileobj(res, out, 1024 * 1024)
    if archive.stat().st_size != asset.size or _sha256(archive) != asset.sha256:
        archive.unlink(missing_ok=True)
        raise LlamaRuntimeError(f"{asset.filename} 驗證失敗（大小或 SHA-256 不符），請重新執行下載。")

    staging = final.parent / f".{final.name}.partial"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    extract_archive(archive, asset.filename, staging)
    exe = next(iter(sorted(staging.rglob(exe_name()))), None)
    if exe is None:
        shutil.rmtree(staging, ignore_errors=True)
        raise LlamaRuntimeError(f"{asset.filename} 中找不到 {exe_name()}。")
    if sys.platform != "win32":
        exe.chmod(0o755)
    (staging / MARKER).write_text(
        json.dumps({"tag": release.tag, "commit": release.commit, "asset": asset.filename, "sha256": asset.sha256}, indent=2),
        encoding="utf-8",
    )
    if final.exists():
        shutil.rmtree(final)
    staging.rename(final)
    archive.unlink(missing_ok=True)
    installed = find_llama_server(runtime_root, release)
    if installed is None:  # pragma: no cover - 剛寫入的標記一定讀得到
        raise LlamaRuntimeError("llama.cpp 安裝後找不到執行檔。")
    on_progress(f"llama.cpp {release.tag}：已安裝到 {final}")
    return installed
