"""模型管理（PROJECT_SPEC §7、Phase 09）：下載（進度、取消、續傳）、完整性驗證、刪除、版本更新、清除不再使用的檔案。

- 以「套件」為單位，使用者看到的是功能：
    語音辨識 = Qwen3-ASR ＋ Qwen3-ForcedAligner（使用者決定：對齊模型是必要的，一起安裝、一起刪除）
    摘要與心智圖 = Qwen3.5-4B（GGUF）＋ llama.cpp 執行檔
- 一次只做一個下載／驗證工作（背景執行緒＋佇列）；狀態由 GET /api/models 輪詢。
- 只在使用者按下按鈕時連網；已安裝的模型完全離線使用（規格 §7.2）。
- 刪除或換新版本時要取得 MODEL_LOCK：語音辨識或摘要正在使用模型時不能動它的檔案（Windows 也無法刪除開啟中的檔案）。
- 版本：登錄表的 revision 改變（程式更新）時，已安裝的舊版本顯示「需要更新」；更新時相同的檔案（雜湊一致）會沿用，不重新下載。
"""
from __future__ import annotations

import shutil
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.keepawake import KEEP_AWAKE
from app.models.fetch import FetchCancelled
from app.models.registry import ALL_MODELS, LLM_MODEL, QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B, ModelSpec
from app.models.runtime import (
    LLAMA_CPP,
    LlamaRuntimeError,
    asset_for,
    CPU,
    CUDA,
    download_runtime,
    find_llama_server,
    install_dir,
    runtime_size,
    variant_platform,
)
from app.models.store import (
    MARKER,
    InstallCancelled,
    ModelError,
    dir_size,
    install,
    installed_revision,
    is_installed,
    staged_bytes,
    staging_dir,
    verify_installed,
)
from app.services.model_lock import MODEL_LOCK

PackageId = Literal["asr", "llm", "llm_gpu"]
JobAction = Literal["download", "verify"]


@dataclass(frozen=True)
class Package:
    id: PackageId
    name: str
    role: str
    hardware: str
    models: tuple[ModelSpec, ...]
    runtime: bool = False
    #: llama.cpp 的版本：cpu（預設；macOS 內建 Metal）或 cuda（Phase 10 的 GPU 加速）
    runtime_variant: str = CPU
    #: 選用（不在「全部下載」裡，只在硬體支援時顯示）
    optional: bool = False


PACKAGES: tuple[Package, ...] = (
    Package(
        "asr",
        "語音辨識",
        "把影片或錄音轉成逐字稿，並對齊每一句的時間（Qwen3-ASR ＋ 時間戳記對齊模型）。",
        "建議記憶體 8 GB 以上；只用 CPU 即可，24 分鐘的錄音約需 30 分鐘。",
        (QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B),
    ),
    Package(
        "llm",
        "摘要與心智圖",
        "整理逐字稿，產生摘要、重點、行動事項與心智圖（Qwen3.5-4B，使用 llama.cpp 執行）。",
        "建議記憶體 8 GB 以上（執行時約使用 3.5 GB）；只用 CPU 即可。",
        (LLM_MODEL,),
        runtime=True,
    ),
)
BY_PACKAGE = {p.id: p for p in PACKAGES}

#: Phase 10：NVIDIA GPU 加速摘要（CUDA 版 llama.cpp）。只在偵測到可用的 NVIDIA GPU、而且 CUDA 版已固定版本時顯示。
LLM_GPU = Package(
    "llm_gpu",
    "摘要 GPU 加速（NVIDIA）",
    "用 NVIDIA 顯示卡執行摘要與心智圖，通常比 CPU 快很多。需要先安裝「摘要與心智圖」；GPU 無法使用時會自動改用 CPU。",
    "需要 NVIDIA 顯示卡（建議顯示記憶體 4 GB 以上）與較新的驅動程式。",
    (),
    runtime=True,
    runtime_variant=CUDA,
    optional=True,
)


def optional_packages() -> list[Package]:
    """依硬體決定要顯示的選用套件（測試可替換）。"""
    try:
        from app.core.hardware import detect
        from app.core.runtime_select import cuda_build_ok

        plat = variant_platform(CUDA)
        if plat and cuda_build_ok(detect(), plat)[0]:
            return [LLM_GPU]
    except Exception:  # noqa: BLE001 - 偵測失敗時不顯示選用套件
        pass
    return []


class ManagerError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Job:
    package: PackageId
    action: JobAction
    status: Literal["queued", "running"] = "queued"
    stage: str = "等待中"
    current: str = ""
    done: int = 0
    total: int = 0
    speed: float = 0.0  # bytes/s（下載時）
    started: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event)
    #: 驗證失敗後的「修復」：已安裝的檔案也重新檢查，壞掉的重新下載
    repair: bool = False
    _last_t: float = 0.0
    _last_done: int = 0

    def add(self, n: int) -> None:
        self.done = max(0, min(self.total, self.done + n)) if self.total else self.done + n
        now = time.monotonic()
        if now - self._last_t >= 1.0:
            rate = (self.done - self._last_done) / (now - self._last_t) if self._last_t else 0.0
            self.speed = rate if self.speed == 0 else 0.7 * self.speed + 0.3 * rate
            self._last_t, self._last_done = now, self.done


@dataclass
class LastResult:
    action: JobAction
    ok: bool
    message: str
    at: float
    problems: list[str] = field(default_factory=list)


class ModelManager:
    def __init__(self, models_root: Path, runtime_root: Path) -> None:
        self.models_root = models_root
        self.runtime_root = runtime_root
        self._lock = threading.Lock()
        self._queue: deque[Job] = deque()
        self._current: Job | None = None
        self._last: dict[str, LastResult] = {}
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopping = False

    # ------------------------------------------------------------------ 狀態

    def _plat(self, p: Package | None = None) -> str | None:
        return variant_platform(p.runtime_variant if p else CPU)

    def _runtime_installed(self, p: Package | None = None) -> bool:
        return find_llama_server(self.runtime_root, plat=self._plat(p)) is not None

    def _runtime_supported(self, p: Package | None = None) -> bool:
        return bool(LLAMA_CPP.tag) and asset_for(LLAMA_CPP, self._plat(p)) is not None

    def packages(self) -> list[Package]:
        return [*PACKAGES, *optional_packages()]

    def _by_id(self, pid: str) -> Package | None:
        return next((p for p in self.packages() if p.id == pid), None)

    def package_installed(self, p: Package) -> bool:
        return all(is_installed(m, self.models_root) for m in p.models) and (not p.runtime or self._runtime_installed(p))

    def _missing_bytes(self, p: Package) -> int:
        total = 0
        for m in p.models:
            if is_installed(m, self.models_root):
                continue
            staged = staging_dir(m, self.models_root)
            have = staged_bytes(staged, m.files)
            total += m.size_bytes - have
        if p.runtime and not self._runtime_installed(p):
            total += runtime_size(plat=self._plat(p))
        return total

    def _status(self, p: Package) -> str:
        job = self._job_for(p.id)
        if job is not None:
            return "verifying" if job.action == "verify" else ("queued" if job.status == "queued" else "downloading")
        if self.package_installed(p):
            last = self._last.get(p.id)
            return "damaged" if last and last.action == "verify" and not last.ok else "installed"
        if any(installed_revision(m, self.models_root) not in (None, m.revision) for m in p.models):
            return "outdated"
        if any(staging_dir(m, self.models_root).exists() for m in p.models):
            return "partial"
        return "not_installed"

    def _job_for(self, pid: str) -> Job | None:
        if self._current and self._current.package == pid:
            return self._current
        return next((j for j in self._queue if j.package == pid), None)

    def unused(self) -> list[dict[str, Any]]:
        """不再使用的模型與執行檔（舊版本、Phase 06 比較用的候選模型、中斷留下的暫存）。"""
        keep_models = {m.local_dir(self.models_root).resolve() for m in ALL_MODELS}
        keep_models |= {staging_dir(m, self.models_root).resolve() for m in ALL_MODELS}
        items: list[dict[str, Any]] = []
        for kind_dir in sorted(p for p in self.models_root.glob("*") if p.is_dir()):
            for d in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
                if d.resolve() not in keep_models:
                    items.append({"key": f"models/{kind_dir.name}/{d.name}", "label": d.name.lstrip(".").removesuffix(".partial"), "kind": kind_dir.name, "size_bytes": dir_size(d), "partial": d.name.endswith(".partial")})
        llama = self.runtime_root / "llama"
        if llama.is_dir():
            current_dirs = {install_dir(self.runtime_root, plat=self._plat(p)).resolve() for p in [*PACKAGES, LLM_GPU] if p.runtime}
            for d in sorted(llama.iterdir()):
                if d.is_dir() and d.resolve() not in current_dirs and not any(d.name == f".{c.name}.partial" for c in current_dirs):
                    items.append({"key": f"runtime/llama/{d.name}", "label": f"llama.cpp {d.name.lstrip('.')}", "kind": "runtime", "size_bytes": dir_size(d), "partial": d.name.endswith(".partial")})
        return items

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            packages = []
            for p in self.packages():
                job = self._job_for(p.id)
                last = self._last.get(p.id)
                models = [
                    {
                        "id": m.id,
                        "kind": m.kind,
                        "display_name": m.display_name,
                        "role": m.role,
                        "repo": m.repo,
                        "revision": m.revision,
                        "license": m.license,
                        "size_bytes": m.size_bytes,
                        "installed": is_installed(m, self.models_root),
                        "installed_revision": installed_revision(m, self.models_root),
                    }
                    for m in p.models
                ]
                runtime = (
                    {
                        "name": "llama.cpp" if p.runtime_variant == CPU else "llama.cpp（CUDA 版）",
                        "version": LLAMA_CPP.tag,
                        "size_bytes": runtime_size(plat=self._plat(p)),
                        "installed": self._runtime_installed(p),
                        "supported": self._runtime_supported(p),
                    }
                    if p.runtime
                    else None
                )
                packages.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "role": p.role,
                        "hardware": p.hardware,
                        "status": self._status(p),
                        "size_bytes": sum(m.size_bytes for m in p.models) + (runtime_size(plat=self._plat(p)) if p.runtime else 0),
                        "optional": p.optional,
                        "missing_bytes": self._missing_bytes(p),
                        "models": models,
                        "runtime": runtime,
                        "job": None
                        if job is None
                        else {
                            "action": job.action,
                            "status": job.status,
                            "stage": job.stage,
                            "current": job.current,
                            "done_bytes": job.done,
                            "total_bytes": job.total,
                            "speed": round(job.speed),
                            "cancelling": job.cancel.is_set(),
                        },
                        "last": None
                        if last is None
                        else {"action": last.action, "ok": last.ok, "message": last.message, "at": last.at, "problems": last.problems},
                    }
                )
            self.models_root.mkdir(parents=True, exist_ok=True)
            return {
                "models_dir": str(self.models_root),
                "free_bytes": shutil.disk_usage(self.models_root).free,
                "packages": packages,
                "unused": self.unused(),
                "busy": self._current is not None or bool(self._queue),
            }

    # ------------------------------------------------------------------ 動作

    def request(self, pid: str, action: JobAction) -> None:
        p = self._by_id(pid)
        if p is None:
            raise ManagerError(404, "沒有這個模型。")
        with self._lock:
            if self._job_for(p.id) is not None:
                raise ManagerError(409, f"{p.name}已在處理中。")
            if action == "download":
                if p.runtime and not self._runtime_installed(p) and not self._runtime_supported(p):
                    raise ManagerError(422, "這個作業系統目前沒有可用的 llama.cpp 執行檔（macOS 版本在 Phase 11 提供）。")
                repair = self._status(p) == "damaged"
                if self.package_installed(p) and not repair:
                    raise ManagerError(409, f"{p.name}已安裝。")
            elif not self.package_installed(p):
                raise ManagerError(409, f"{p.name}尚未安裝，無法驗證。")
            else:
                repair = False
            self._last.pop(p.id, None)
            self._queue.append(Job(package=p.id, action=action, repair=repair))
            self._ensure_worker()
        self._wake.set()

    def download_all(self) -> list[str]:
        queued = []
        for p in PACKAGES:  # 選用套件（GPU 加速）不包含在「全部下載」
            if not self.package_installed(p) and self._job_for(p.id) is None:
                try:
                    self.request(p.id, "download")
                    queued.append(p.id)
                except ManagerError:
                    pass
        return queued

    def cancel(self, pid: str) -> None:
        with self._lock:
            job = self._job_for(pid)
            if job is None:
                raise ManagerError(409, "沒有進行中的工作。")
            if job.status == "queued":
                self._queue.remove(job)
                self._last[pid] = LastResult(job.action, False, "已取消。", time.time())
            else:
                job.cancel.set()

    def delete(self, pid: str) -> None:
        p = self._by_id(pid)
        if p is None:
            raise ManagerError(404, "沒有這個模型。")
        with self._lock:
            if self._job_for(p.id) is not None:
                raise ManagerError(409, f"{p.name}正在下載或驗證，請先取消。")
            if not MODEL_LOCK.acquire(blocking=False):
                raise ManagerError(409, "語音辨識或摘要正在使用模型，請等它完成後再刪除。")
            try:
                for m in p.models:
                    self._rm(m.local_dir(self.models_root))
                    self._rm(staging_dir(m, self.models_root))
                if p.runtime:
                    d = install_dir(self.runtime_root, plat=self._plat(p))
                    self._rm(d)
                    self._rm(d.parent / f".{d.name}.partial")
                    for f in d.parent.glob(".*.partial") if d.parent.exists() else []:
                        if f.is_file():
                            f.unlink(missing_ok=True)
                self._last.pop(p.id, None)
            finally:
                MODEL_LOCK.release()

    def delete_unused(self, key: str) -> None:
        item = next((u for u in self.unused() if u["key"] == key), None)
        if item is None:
            raise ManagerError(404, "找不到這個項目。")
        base = self.models_root if key.startswith("models/") else self.runtime_root
        rel = key.split("/", 1)[1]
        self._rm(base / rel, root=base)

    def _rm(self, path: Path, root: Path | None = None) -> None:
        """只刪除 models_root / runtime_root 底下的資料夾或檔案。"""
        roots = [root] if root else [self.models_root, self.runtime_root]
        if not path.exists():
            return
        resolved = path.resolve()
        if not any(resolved != r.resolve() and resolved.is_relative_to(r.resolve()) for r in roots):
            raise ManagerError(400, "路徑不在模型資料夾內。")
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except PermissionError:
            raise ManagerError(409, "檔案正在使用中（或被防毒軟體鎖定），請稍後再試。") from None

    def shutdown(self) -> None:
        self._stopping = True
        with self._lock:
            if self._current:
                self._current.cancel.set()
            self._queue.clear()
        self._wake.set()

    # ------------------------------------------------------------------ 背景工作

    def _ensure_worker(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="model-manager", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stopping:
            with self._lock:
                job = self._queue.popleft() if self._queue else None
                self._current = job
                if job:
                    job.status = "running"
                    job.started = time.monotonic()
            if job is None:
                self._wake.wait(timeout=1.0)
                self._wake.clear()
                continue
            p = self._by_id(job.package) or BY_PACKAGE[job.package]  # type: ignore[index]
            KEEP_AWAKE.acquire()  # 下載數 GB 需要一段時間：期間不讓電腦因閒置而睡眠
            try:
                if job.action == "download":
                    self._download(p, job)
                    result = LastResult("download", True, "下載完成並通過驗證。", time.time())
                else:
                    problems = self._verify(p, job)
                    msg = "所有檔案都完整。" if not problems else "有檔案損壞或遺失，請按「修復」重新下載。"
                    result = LastResult("verify", not problems, msg, time.time(), problems)
            except (InstallCancelled, FetchCancelled):
                result = LastResult(job.action, False, "已取消。已下載的部分會保留，下次可以繼續。", time.time())
            except (ModelError, LlamaRuntimeError, ManagerError) as e:
                result = LastResult(job.action, False, getattr(e, "message", None) or str(e), time.time())
            except Exception as e:  # noqa: BLE001 - 背景執行緒不能讓錯誤消失
                result = LastResult(job.action, False, f"發生未預期的錯誤：{e}", time.time())
            finally:
                KEEP_AWAKE.release()
            with self._lock:
                self._last[p.id] = result
                self._current = None

    @contextmanager
    def _model_lock(self, job: Job) -> Iterator[None]:
        """換資料夾時：等語音辨識／摘要用完模型（可取消）。"""
        job.stage = "等待其他 AI 工作完成"
        while not MODEL_LOCK.acquire(timeout=0.5):
            if job.cancel.is_set():
                raise InstallCancelled()
        try:
            yield
        finally:
            MODEL_LOCK.release()

    def _download(self, p: Package, job: Job) -> None:
        todo = [m for m in p.models if job.repair or not is_installed(m, self.models_root)]
        # 已安裝但損壞（驗證失敗）或舊版本：把現有檔案移到暫存資料夾，雜湊一致的檔案沿用、不重新下載
        for m in p.models:
            final = m.local_dir(self.models_root)
            if final.exists() and (m in todo or installed_revision(m, self.models_root) != m.revision):
                if m not in todo:
                    todo.append(m)
                with self._model_lock(job):
                    staged = staging_dir(m, self.models_root)
                    staged.mkdir(parents=True, exist_ok=True)
                    for f in m.files:
                        src, dst = final / f.name, staged / f.name
                        if src.is_file() and not dst.exists():
                            src.replace(dst)
                    shutil.rmtree(final, ignore_errors=True)
        need_runtime = p.runtime and not self._runtime_installed(p)
        job.total = sum(m.size_bytes for m in todo) + (runtime_size(plat=self._plat(p)) if need_runtime else 0)
        # 先前下載到一半的部分
        for m in todo:
            staged = staging_dir(m, self.models_root)
            job.done += staged_bytes(staged, m.files)

        def stage(s: str, name: str) -> None:
            job.stage = {"downloading": "下載中", "verifying": "驗證檔案", "installing": "安裝中"}.get(s, s)
            if name:
                job.current = name

        for m in todo:
            job.current = m.display_name
            install(m, self.models_root, job.add, job.cancel.is_set, stage, lambda: self._model_lock(job))
        if need_runtime:
            job.stage, job.current = "下載中", f"llama.cpp {LLAMA_CPP.tag}"
            download_runtime(
                self.runtime_root, on_progress=lambda s: None, on_bytes=job.add, is_cancelled=job.cancel.is_set, plat=self._plat(p)
            )
        job.stage = "完成"

    def _verify(self, p: Package, job: Job) -> list[str]:
        job.stage = "驗證檔案"
        job.total = sum(m.size_bytes for m in p.models)
        problems: list[str] = []
        for m in p.models:
            job.current = m.display_name

            def on_bytes(n: int) -> None:
                if job.cancel.is_set():
                    raise InstallCancelled()
                job.add(n)

            problems += [f"{m.display_name}：{e}" for e in verify_installed(m, self.models_root, on_bytes)]
            marker = m.local_dir(self.models_root) / MARKER
            if not marker.is_file():
                problems.append(f"{m.display_name}：缺少安裝紀錄")
        if p.runtime and not self._runtime_installed(p):
            problems.append("llama.cpp 執行檔遺失")
        return problems
