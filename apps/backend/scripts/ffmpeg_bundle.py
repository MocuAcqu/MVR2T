"""準備安裝程式內附的 FFmpeg（Phase 11，使用者決定：內附在安裝程式中）。

使用 BtbN/FFmpeg-Builds 的 **LGPL** 版（win64-lgpl，不含 GPL 元件；本程式只需要解碼、重新取樣與 silencedetect）。
這個組建以 --enable-version3 編譯（附 LGPL 第 3 版全文），授權是 **LGPL-3.0-or-later**（Phase 11 Windows 驗收時以 ffmpeg -L 確認）。
GitHub API 目前把下載網址轉到 FFmpeg-Builds/FFmpeg-Builds（舊網址會自動轉址）；pin 記錄的是 API 回傳的網址。
版本固定在 packaging/ffmpeg.json（檔名、大小、SHA-256）：不使用每天變動的 latest。

用法（在 apps/backend，需要網路）：
    python -m scripts.ffmpeg_bundle --resolve     # 查出最新的 7.1 系列 LGPL 版並寫入 packaging/ffmpeg.json（更新版本時）
    python -m scripts.ffmpeg_bundle               # 依 packaging/ffmpeg.json 下載、驗證，解壓到 apps/desktop/build-resources/ffmpeg/

輸出：ffmpeg.exe、ffprobe.exe、LICENSE.txt、SOURCE.txt（原始碼位置，LGPL 要求）。electron-builder 會放進 resources/ffmpeg/。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from app.models.fetch import FetchError, fetch

BACKEND = Path(__file__).resolve().parents[1]
PIN = BACKEND / "packaging" / "ffmpeg.json"
OUT = BACKEND.parent / "desktop" / "build-resources" / "ffmpeg"
CACHE = BACKEND / "build" / "ffmpeg"
API = "https://api.github.com/repos/BtbN/FFmpeg-Builds"
SERIES = "7.1"
ASSET_RE = re.compile(rf"^ffmpeg-n{re.escape(SERIES)}[.\d]*-\d+-g[0-9a-f]+-win64-lgpl-{re.escape(SERIES)}\.zip$")
WANTED = ("ffmpeg.exe", "ffprobe.exe")
LICENSE_ID = "LGPL-3.0-or-later"


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "MVR2T"})
    with urllib.request.urlopen(req, timeout=60) as res:  # noqa: S310 - fixed https URL
        return json.loads(res.read().decode("utf-8"))


def pick_asset(releases: list[dict]) -> tuple[dict, dict] | None:
    """最新的 autobuild release 中，7.1 系列的 win64 LGPL 靜態版（不是 latest、不是 shared）。"""
    for rel in releases:
        if not str(rel.get("tag_name", "")).startswith("autobuild-"):
            continue
        for a in rel.get("assets", []):
            if ASSET_RE.match(a["name"]):
                return rel, a
    return None


def check_license(text: str) -> str | None:
    """內附的必須是 LGPL 版：LICENSE.txt 要是 LGPL 全文（GPL 版的 LICENSE 是 GPL，會被擋下）。"""
    head = text[:2000].upper()
    if "LESSER GENERAL PUBLIC LICENSE" not in head:
        return "LICENSE.txt 不是 LGPL（可能下載到 GPL 版）。安裝程式只能內附 LGPL 版，已停止。"
    return None


def resolve() -> int:
    releases = _get(f"{API}/releases?per_page=20")
    assert isinstance(releases, list)
    found = pick_asset(releases)
    if found is None:
        print(f"找不到 n{SERIES} 的 win64-lgpl 壓縮檔。", file=sys.stderr)
        return 1
    rel, a = found
    digest = str(a.get("digest") or "")
    if digest.startswith("sha256:"):
        sha = digest.split(":", 1)[1]
    else:
        h = hashlib.sha256()
        with urllib.request.urlopen(a["browser_download_url"], timeout=120) as res:  # noqa: S310
            while chunk := res.read(1024 * 1024):
                h.update(chunk)
        sha = h.hexdigest()
    version = re.search(r"ffmpeg-(n[\w.-]+?)-win64", a["name"])
    pin = {
        "release": rel["tag_name"],
        "filename": a["name"],
        "size": a["size"],
        "sha256": sha,
        "url": a["browser_download_url"],
        "version": version.group(1) if version else "",
        "license": LICENSE_ID,
        "source": "https://github.com/FFmpeg/FFmpeg（版本見 version；組建腳本 https://github.com/BtbN/FFmpeg-Builds）",
    }
    PIN.write_text(json.dumps(pin, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(pin, ensure_ascii=False, indent=2))
    print(f"已寫入 {PIN}")
    return 0


def prepare() -> int:
    if not PIN.is_file():
        print(f"沒有 {PIN}。請先執行 python -m scripts.ffmpeg_bundle --resolve。", file=sys.stderr)
        return 1
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / pin["filename"]
    cached = archive.is_file() and archive.stat().st_size == int(pin["size"])
    if cached:
        print(f"使用快取：{archive}", flush=True)
    else:
        print(f"下載 {pin['filename']}（{pin['size'] / 1024**2:,.1f} MB）…", flush=True)
    try:
        fetch(pin["url"], archive, int(pin["size"]))
    except FetchError as e:
        print(f"下載失敗：{e}", file=sys.stderr)
        return 1
    h = hashlib.sha256()
    with archive.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    if h.hexdigest() != pin["sha256"]:
        archive.unlink(missing_ok=True)
        print("SHA-256 不符，已刪除下載的檔案，請重新執行。", file=sys.stderr)
        return 1
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if info.is_dir():
                continue
            if name in WANTED or name.upper() == "LICENSE.TXT":
                (OUT / name).write_bytes(z.read(info))
    missing = [n for n in (*WANTED, "LICENSE.txt") if not (OUT / n).is_file()]
    if missing:
        print(f"壓縮檔中缺少：{', '.join(missing)}", file=sys.stderr)
        return 1
    problem = check_license((OUT / "LICENSE.txt").read_text(encoding="utf-8", errors="replace"))
    if problem:
        shutil.rmtree(OUT, ignore_errors=True)
        print(problem, file=sys.stderr)
        return 1
    (OUT / "SOURCE.txt").write_text(
        f"FFmpeg {pin['version']}（{pin['license']}）\n"
        f"Build: {pin['filename']}（{pin['release']}，SHA-256 {pin['sha256']}）\n"
        f"Source: {pin['source']}\n",
        encoding="utf-8",
    )
    print(f"完成：{OUT}（{', '.join(sorted(p.name for p in OUT.iterdir()))}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Prepare the bundled LGPL FFmpeg for the Windows installer.")
    p.add_argument("--resolve", action="store_true", help="pin the newest n7.1 win64-lgpl build in packaging/ffmpeg.json")
    args = p.parse_args(argv)
    return resolve() if args.resolve else prepare()


if __name__ == "__main__":
    raise SystemExit(main())
