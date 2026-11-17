"""YouTube 下載元件（yt-dlp）的安裝與更新（使用者決定 2026-11-15）。

- 不放在安裝程式中：使用者在「模型管理」按需下載（約 18 MB），裝在 <userData>/runtime/yt-dlp/。
- **例外於「依賴版本至少發布 2 週」的規則**（使用者同意）：YouTube 常改版，舊版 yt-dlp 很快會失效，
  所以安裝與更新都取官方 GitHub 的最新正式版（releases/latest），以同一個 release 的 SHA2-256SUMS 驗證檔案。
- 官方的單一執行檔（yt-dlp.exe／yt-dlp_macos／yt-dlp_linux）已內含 YouTube 需要的 EJS 解題程式（yt-dlp-ejs）。
- 只在使用者按下按鈕時連網；狀態由 GET /api/youtube/component 輪詢。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.models.fetch import USER_AGENT, FetchCancelled, FetchError, fetch

LATEST_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
SUMS_NAME = "SHA2-256SUMS"
LICENSE = "Unlicense（公有領域）"
INFO_FILE = "install.json"


class YtDlpError(Exception):
    """給使用者看的錯誤（繁體中文）。"""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def asset_name(plat: str | None = None, machine: str | None = None) -> str | None:
    """這個作業系統要下載的官方單一執行檔名稱。"""
    plat = plat or sys.platform
    machine = (machine or platform.machine()).lower()
    if plat == "win32":
        return "yt-dlp.exe" if machine in ("amd64", "x86_64", "arm64", "aarch64") else "yt-dlp_x86.exe"
    if plat == "darwin":
        return "yt-dlp_macos"
    if plat.startswith("linux"):
        return "yt-dlp_linux_aarch64" if machine in ("aarch64", "arm64") else "yt-dlp_linux"
    return None


def exe_name(plat: str | None = None) -> str:
    return "yt-dlp.exe" if (plat or sys.platform) == "win32" else "yt-dlp"


@dataclass(frozen=True)
class Release:
    version: str
    asset: str
    url: str
    size: int
    sha256: str
    published_at: str = ""


def parse_sums(text: str) -> dict[str, str]:
    """SHA2-256SUMS：每行「<sha256>  <檔名>」（檔名前可能有 *）。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            out[parts[-1].lstrip("*")] = parts[0].lower()
    return out


def _get(url: str, accept: str = "application/vnd.github+json") -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310 - fixed https URL
            return res.read()
    except Exception as e:  # noqa: BLE001 - 轉成使用者看得懂的訊息
        raise YtDlpError("無法連線到 GitHub 取得 yt-dlp 的最新版本，請檢查網路後再試。", 503) from e


def resolve_latest(get: Callable[[str], bytes] = _get, asset: str | None = None) -> Release:
    """查詢官方最新正式版：版本、下載網址、大小與 SHA-256（來自同一 release 的 SHA2-256SUMS）。"""
    want = asset or asset_name()
    if want is None:
        raise YtDlpError("這個作業系統沒有官方的 yt-dlp 執行檔。", 422)
    data = json.loads(get(LATEST_URL).decode("utf-8"))
    assets = {a["name"]: a for a in data.get("assets", [])}
    a = assets.get(want)
    sums = assets.get(SUMS_NAME)
    if a is None or sums is None:
        raise YtDlpError(f"最新版的 yt-dlp 沒有 {want} 或 {SUMS_NAME}，請稍後再試。", 502)
    sha = parse_sums(get(sums["browser_download_url"]).decode("utf-8", "replace")).get(want)
    if not sha:
        raise YtDlpError(f"{SUMS_NAME} 中找不到 {want} 的雜湊值。", 502)
    digest = str(a.get("digest") or "")
    if digest.startswith("sha256:") and digest.split(":", 1)[1].lower() != sha:
        raise YtDlpError("yt-dlp 的雜湊值不一致（GitHub 與 SHA2-256SUMS 不同），已停止。", 502)
    return Release(
        version=str(data.get("tag_name", "")),
        asset=want,
        url=a["browser_download_url"],
        size=int(a["size"]),
        sha256=sha,
        published_at=str(data.get("published_at", "")),
    )


Phase = Literal["idle", "checking", "downloading", "installing"]


class YtDlpComponent:
    """安裝、更新、刪除 yt-dlp；一次只做一件事（背景執行緒）。"""

    def __init__(self, runtime_root: Path, resolver: Callable[[], Release] | None = None) -> None:
        self.dir = runtime_root / "yt-dlp"
        self._resolve = resolver or resolve_latest
        self._lock = threading.Lock()
        self._phase: Phase = "idle"
        self._done = 0
        self._total = 0
        self._speed = 0.0  # bytes/s（下載時；Windows 實測 23 MB 約 159 秒，要讓使用者看到速度與剩餘時間）
        self._last_t = 0.0
        self._last_done = 0
        self._cancel = threading.Event()
        self._latest: Release | None = None
        self._checked_at: float | None = None
        self._message: str | None = None
        self._ok: bool | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ 狀態

    @property
    def exe(self) -> Path:
        return self.dir / exe_name()

    def installed_info(self) -> dict[str, Any] | None:
        info = self.dir / INFO_FILE
        if not (self.exe.is_file() and info.is_file()):
            return None
        try:
            return json.loads(info.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def executable(self) -> Path | None:
        return self.exe if self.installed_info() is not None else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            info = self.installed_info()
            latest = self._latest
            update = bool(info and latest and latest.version != info.get("version"))
            return {
                "installed": info is not None,
                "version": info.get("version") if info else None,
                "installed_at": info.get("installed_at") if info else None,
                "supported": asset_name() is not None,
                "latest_version": latest.version if latest else None,
                "update_available": update,
                "checked_at": self._checked_at,
                "size_bytes": latest.size if latest else (info.get("size") if info else None),
                "license": LICENSE,
                "job": None
                if self._phase == "idle"
                else {
                    "phase": self._phase,
                    "done_bytes": self._done,
                    "total_bytes": self._total,
                    "speed": round(self._speed),
                    "cancelling": self._cancel.is_set(),
                },
                "last": None if self._ok is None else {"ok": self._ok, "message": self._message},
            }

    # ------------------------------------------------------------------ 動作

    def _start(self, phase: Phase, fn: Callable[[], str]) -> None:
        with self._lock:
            if self._phase != "idle":
                raise YtDlpError("YouTube 下載元件正在處理中。")
            self._phase, self._done, self._total = phase, 0, 0
            self._speed, self._last_t, self._last_done = 0.0, 0.0, 0
            self._cancel.clear()
            self._ok = self._message = None

        def run() -> None:
            ok, msg = True, ""
            try:
                msg = fn()
            except FetchCancelled:
                ok, msg = False, "已取消。"
            except (YtDlpError, FetchError) as e:
                ok, msg = False, getattr(e, "message", None) or str(e)
            except Exception as e:  # noqa: BLE001 - 背景執行緒不能讓錯誤消失
                ok, msg = False, f"發生未預期的錯誤：{e}"
            with self._lock:
                self._phase, self._ok, self._message = "idle", ok, msg

        self._thread = threading.Thread(target=run, name="yt-dlp-component", daemon=True)
        self._thread.start()

    def check(self) -> None:
        """查詢最新版本（不下載）。"""

        def job() -> str:
            rel = self._check_latest()
            info = self.installed_info()
            if info and info.get("version") == rel.version:
                return f"已是最新版（{rel.version}）。"
            return f"有新版本：{rel.version}。" if info else f"最新版本：{rel.version}。"

        self._start("checking", job)

    def install(self) -> None:
        """安裝或更新到最新版。"""
        self._start("checking", self._install_latest)

    def cancel(self) -> None:
        with self._lock:
            if self._phase == "idle":
                raise YtDlpError("沒有進行中的工作。")
            self._cancel.set()

    def delete(self, in_use: Callable[[], bool] = lambda: False) -> None:
        with self._lock:
            if self._phase != "idle":
                raise YtDlpError("YouTube 下載元件正在處理中，請先取消。")
            if in_use():
                raise YtDlpError("正在下載 YouTube 影片，請等它完成後再刪除。")
            if self.dir.exists():
                try:
                    shutil.rmtree(self.dir)
                except PermissionError:
                    raise YtDlpError("檔案正在使用中（或被防毒軟體鎖定），請稍後再試。") from None
            self._ok = self._message = None

    def wait(self, timeout: float = 30.0) -> None:
        """測試用：等背景工作結束。"""
        t = self._thread
        if t is not None:
            t.join(timeout)

    # ------------------------------------------------------------------ 背景工作

    def _check_latest(self) -> Release:
        rel = self._resolve()
        with self._lock:
            self._latest, self._checked_at = rel, time.time()
        return rel

    def _install_latest(self) -> str:
        rel = self._check_latest()
        info = self.installed_info()
        if info and info.get("version") == rel.version and info.get("sha256") == rel.sha256:
            return f"已是最新版（{rel.version}）。"
        with self._lock:
            self._phase, self._total = "downloading", rel.size
        self.dir.mkdir(parents=True, exist_ok=True)
        part = self.dir / f".{rel.asset}.{rel.version}.partial"

        def on_bytes(n: int) -> None:
            with self._lock:
                self._done = max(0, self._done + n)
                now = time.monotonic()
                if not self._last_t:
                    self._last_t, self._last_done = now, self._done
                elif now - self._last_t >= 1.0:
                    rate = (self._done - self._last_done) / (now - self._last_t)
                    self._speed = rate if self._speed == 0 else 0.7 * self._speed + 0.3 * rate
                    self._last_t, self._last_done = now, self._done

        fetch(rel.url, part, rel.size, on_bytes, self._cancel.is_set)
        with self._lock:
            self._phase = "installing"
        h = hashlib.sha256()
        with part.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        if h.hexdigest() != rel.sha256:
            part.unlink(missing_ok=True)
            raise YtDlpError("下載的 yt-dlp 檔案雜湊不符，已刪除，請重新下載。", 502)
        if os.name != "nt":
            part.chmod(part.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        try:
            part.replace(self.exe)
        except PermissionError:
            raise YtDlpError("yt-dlp 正在使用中（或被防毒軟體鎖定），請稍後再試。") from None
        (self.dir / INFO_FILE).write_text(
            json.dumps(
                {"version": rel.version, "asset": rel.asset, "sha256": rel.sha256, "size": rel.size, "installed_at": time.time()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        for leftover in self.dir.glob(".*.partial"):
            leftover.unlink(missing_ok=True)
        return f"已{'更新' if info else '安裝'} yt-dlp {rel.version}。"
