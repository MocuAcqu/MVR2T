"""本機模型的下載、驗證與「已安裝」判斷（Phase 05 開發用；Phase 09 的模型管理會沿用這裡）。

- 下載：huggingface_hub 依固定 revision 逐檔下載到暫存資料夾（同磁碟），全部驗證通過後才改名為正式資料夾，
  避免中斷時留下半套模型被誤認為已安裝。
- 已安裝：資料夾內有 .mvr2t-model.json 且記錄的 revision 與登錄表一致，且每個檔案大小正確（快速檢查，不重算雜湊）。
- 完整驗證（重算雜湊）只在下載後與使用者要求時執行。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from app.models.registry import ModelFile, ModelSpec

MARKER = ".mvr2t-model.json"
CHUNK = 8 * 1024 * 1024


class ModelError(Exception):
    """給使用者看的錯誤（繁體中文）。"""


def file_digest(path: Path, algo: str) -> str:
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
    return h.hexdigest()


def verify_file(directory: Path, f: ModelFile) -> str | None:
    """回傳錯誤說明；正確時回傳 None。"""
    p = directory / f.name
    if not p.is_file():
        return f"缺少檔案 {f.name}"
    if p.stat().st_size != f.size:
        return f"{f.name} 大小不符（{p.stat().st_size} ≠ {f.size}）"
    if file_digest(p, f.algo) != f.digest:
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


def verify_installed(spec: ModelSpec, models_root: Path) -> list[str]:
    """重算所有雜湊；回傳問題清單（空 = 完整）。"""
    d = spec.local_dir(models_root)
    return [err for f in spec.files if (err := verify_file(d, f))]


def download(
    spec: ModelSpec,
    models_root: Path,
    on_progress: Callable[[str], None] = print,
) -> Path:
    """下載並驗證；成功後回傳模型資料夾。已安裝則直接回傳。"""
    if not spec.downloadable:
        raise ModelError(f"{spec.display_name} 將在 Phase {spec.available_from_phase} 提供。")
    final = spec.local_dir(models_root)
    if is_installed(spec, models_root):
        on_progress(f"{spec.display_name}：已安裝，略過（{final}）")
        return final

    from huggingface_hub import hf_hub_download  # 延後載入：一般啟動不需要

    staging = final.parent / f".{spec.id}.partial"
    staging.mkdir(parents=True, exist_ok=True)  # 保留上次中斷的部分，huggingface_hub 會續傳
    free = shutil.disk_usage(staging).free
    if free < spec.size_bytes + 500 * 1024**2:
        raise ModelError(f"磁碟空間不足：{spec.display_name} 需要約 {spec.size_bytes / 1024**3:.1f} GB。")

    for f in spec.files:
        if verify_file(staging, f) is None:
            on_progress(f"  {f.name}：已存在且驗證通過")
            continue
        on_progress(f"  下載 {f.name}（{f.size / 1024**2:,.1f} MB）…")
        started = time.monotonic()
        hf_hub_download(repo_id=spec.repo, filename=f.name, revision=spec.revision, local_dir=staging)
        err = verify_file(staging, f)
        if err:
            (staging / f.name).unlink(missing_ok=True)
            raise ModelError(f"{spec.display_name}：{err}。請重新執行下載。")
        on_progress(f"  {f.name}：完成並驗證（{time.monotonic() - started:.0f} 秒）")

    # huggingface_hub 的快取中繼資料不需要保留
    shutil.rmtree(staging / ".cache", ignore_errors=True)
    (staging / MARKER).write_text(
        json.dumps({"id": spec.id, "repo": spec.repo, "revision": spec.revision, "license": spec.license}, indent=2),
        encoding="utf-8",
    )
    if final.exists():
        shutil.rmtree(final)
    staging.rename(final)
    on_progress(f"{spec.display_name}：已安裝到 {final}")
    return final
