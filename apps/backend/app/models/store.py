"""本機模型的下載、驗證與「已安裝」判斷（Phase 05 起；Phase 09 的模型管理與開發用腳本共用）。

- 下載：依固定 revision 從 Hugging Face 逐檔下載（app/models/fetch.py：續傳、取消、進度）到暫存資料夾（同磁碟），
  全部驗證通過後才改名為正式資料夾，避免中斷時留下半套模型被誤認為已安裝。
  Phase 09 起不再使用 huggingface_hub 下載（它無法回報進度與取消）。
- 已安裝：資料夾內有 .mvr2t-model.json 且記錄的 revision 與登錄表一致，且每個檔案大小正確（快速檢查，不重算雜湊）。
- 完整驗證（重算雜湊）只在下載後與使用者要求時執行。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import ContextManager

from app.models.fetch import FetchCancelled, FetchError, fetch
from app.models.registry import ModelFile, ModelSpec

MARKER = ".mvr2t-model.json"
CHUNK = 8 * 1024 * 1024


class ModelError(Exception):
    """給使用者看的錯誤（繁體中文）。"""


#: 下載來源；測試或鏡像站可用環境變數 MVR2T_HF_ENDPOINT 改變
HF_ENDPOINT = os.environ.get("MVR2T_HF_ENDPOINT", "https://huggingface.co").rstrip("/")


class InstallCancelled(Exception):
    pass


def file_url(spec: ModelSpec, f: ModelFile) -> str:
    return f"{HF_ENDPOINT}/{spec.repo}/resolve/{spec.revision}/{f.name}"


def staging_dir(spec: ModelSpec, models_root: Path) -> Path:
    return spec.local_dir(models_root).parent / f".{spec.id}.partial"


def installed_revision(spec: ModelSpec, models_root: Path) -> str | None:
    """已安裝資料夾記錄的 revision（可能是舊版本）；沒有則 None。"""
    try:
        marker = json.loads((spec.local_dir(models_root) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rev = marker.get("revision")
    return rev if isinstance(rev, str) else None


def dir_size(path: Path) -> int:
    total = 0
    if path.is_dir():
        for p in path.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    return total


def file_digest(path: Path, algo: str, on_bytes: Callable[[int], None] | None = None) -> str:
    if algo == "sha256":
        h = hashlib.sha256()
    elif algo == "git-sha1":
        # Git blob 雜湊：sha1("blob <size>\0" + content)，與 Hugging Face 的 blobId 相同
        h = hashlib.sha1()
        h.update(f"blob {path.stat().st_size}\0".encode())
    else:  # pragma: no cover - 登錄表只會有這兩種
        raise ValueError(algo)
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
            if on_bytes is not None:
                on_bytes(len(chunk))
    return h.hexdigest()


def verify_file(directory: Path, f: ModelFile, on_bytes: Callable[[int], None] | None = None) -> str | None:
    """回傳錯誤說明；正確時回傳 None。"""
    p = directory / f.name
    if not p.is_file():
        return f"缺少檔案 {f.name}"
    if p.stat().st_size != f.size:
        return f"{f.name} 大小不符（{p.stat().st_size} ≠ {f.size}）"
    if file_digest(p, f.algo, on_bytes) != f.digest:
        return f"{f.name} 雜湊不符，檔案可能損壞"
    return None


def is_installed(spec: ModelSpec, models_root: Path) -> bool:
    d = spec.local_dir(models_root)
    try:
        marker = json.loads((d / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if marker.get("revision") != spec.revision or marker.get("repo") != spec.repo:
        return False
    return all((d / f.name).is_file() and (d / f.name).stat().st_size == f.size for f in spec.files)


def verify_installed(spec: ModelSpec, models_root: Path, on_bytes: Callable[[int], None] | None = None) -> list[str]:
    """重算所有雜湊；回傳問題清單（空 = 完整）。"""
    d = spec.local_dir(models_root)
    return [err for f in spec.files if (err := verify_file(d, f, on_bytes))]


def install(
    spec: ModelSpec,
    models_root: Path,
    on_bytes: Callable[[int], None] = lambda n: None,
    is_cancelled: Callable[[], bool] = lambda: False,
    on_stage: Callable[[str, str], None] = lambda stage, name: None,
    swap_guard: Callable[[], ContextManager[object]] = nullcontext,
) -> Path:
    """下載並驗證到暫存資料夾，全部通過才換成正式資料夾。中斷後再呼叫會從暫存資料夾續傳。
    on_bytes：新增的下載位元組（續傳時已有的部分也會先回報）；on_stage(stage, 檔名)：downloading / verifying / installing。
    swap_guard：換資料夾時持有的鎖（例如不讓語音辨識同時載入舊檔）。"""
    if not spec.downloadable:
        raise ModelError(f"{spec.display_name} 目前不提供下載。")
    final = spec.local_dir(models_root)
    if is_installed(spec, models_root):
        return final
    staging = staging_dir(spec, models_root)
    staging.mkdir(parents=True, exist_ok=True)
    have = sum(min((staging / f.name).stat().st_size, f.size) for f in spec.files if (staging / f.name).is_file())
    free = shutil.disk_usage(staging).free
    if free < spec.size_bytes - have + 300 * 1024**2:
        need = (spec.size_bytes - have) / 1024**3
        raise ModelError(f"磁碟空間不足：{spec.display_name} 還需要約 {need:.1f} GB（目前剩 {free / 1024**3:.1f} GB）。")
    try:
        for f in spec.files:
            # 暫存資料夾中已有的檔案（續傳、更新版本或修復時沿用的舊檔）驗證不通過就重新下載一次
            for attempt in range(2):
                on_stage("downloading", f.name)
                fetch(file_url(spec, f), staging / f.name, f.size, on_bytes, is_cancelled)
                on_stage("verifying", f.name)
                err = verify_file(staging, f)
                if not err:
                    break
                (staging / f.name).unlink(missing_ok=True)
                on_bytes(-f.size)
                if attempt == 1:
                    raise ModelError(f"{spec.display_name}：{err}。請重新下載。")
            if is_cancelled():
                raise InstallCancelled()
    except FetchCancelled:
        raise InstallCancelled() from None
    except FetchError as e:
        raise ModelError(f"{spec.display_name}：{e}") from None
    on_stage("installing", "")
    shutil.rmtree(staging / ".cache", ignore_errors=True)  # 舊版 huggingface_hub 下載留下的中繼資料
    (staging / MARKER).write_text(
        json.dumps({"id": spec.id, "repo": spec.repo, "revision": spec.revision, "license": spec.license}, indent=2),
        encoding="utf-8",
    )
    with swap_guard():
        if final.exists():
            shutil.rmtree(final)
        staging.rename(final)
    return final


def download(
    spec: ModelSpec,
    models_root: Path,
    on_progress: Callable[[str], None] = print,
) -> Path:
    """開發用腳本：下載並驗證，在終端機顯示進度。已安裝則直接回傳。"""
    final = spec.local_dir(models_root)
    if is_installed(spec, models_root):
        on_progress(f"{spec.display_name}：已安裝，略過（{final}）")
        return final
    done = 0
    last = [0.0]
    started = time.monotonic()

    def bytes_(n: int) -> None:
        nonlocal done
        done += n
        now = time.monotonic()
        if now - last[0] >= 2 or done >= spec.size_bytes:
            last[0] = now
            on_progress(f"  {done / 1024**2:,.0f} / {spec.size_bytes / 1024**2:,.0f} MB")

    def stage(s: str, name: str) -> None:
        if s == "downloading":
            on_progress(f"  下載 {name}…")
        elif s == "verifying":
            on_progress(f"  驗證 {name}…")

    install(spec, models_root, bytes_, on_stage=stage)
    on_progress(f"{spec.display_name}：已安裝到 {final}（{time.monotonic() - started:.0f} 秒）")
    return final
