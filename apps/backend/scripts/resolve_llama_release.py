"""查出 llama.cpp 某個 commit 對應的官方 Release，並印出可貼到 app/models/runtime.py 的設定。

用法（需要網路，GitHub API 不需登入）：
    python -m scripts.resolve_llama_release --commit 0c1e57098bba43ac29e6e3b677cdceebdd22334f
    python -m scripts.resolve_llama_release --tag b7000     # 已知 tag 時

會列出 Windows CPU（win-cpu-x64）與 macOS（macos-arm64）壓縮檔的大小與 SHA-256。
GitHub 有提供 digest 時直接使用；沒有時會下載檔案自行計算。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request

API = "https://api.github.com/repos/ggml-org/llama.cpp"
PLATFORMS = {"win-cpu-x64": r"-bin-win-cpu-x64\.zip$", "macos-arm64": r"-bin-macos-arm64\.zip$"}


def _get(url: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "MVR2T"})
    with urllib.request.urlopen(req, timeout=60) as res:  # noqa: S310 - fixed https URL
        return json.loads(res.read().decode("utf-8"))


def find_tag(commit: str, pages: int = 30) -> str | None:
    for page in range(1, pages + 1):
        tags = _get(f"{API}/tags?per_page=100&page={page}")
        assert isinstance(tags, list)
        if not tags:
            return None
        for t in tags:
            if t["commit"]["sha"].startswith(commit):
                return str(t["name"])
    return None


def sha256_of(url: str) -> str:
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "MVR2T"})
    with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310
        while chunk := res.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Resolve a pinned llama.cpp release.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--commit")
    g.add_argument("--tag")
    args = p.parse_args(argv)

    tag = args.tag or find_tag(args.commit)
    if not tag:
        print(f"找不到 commit {args.commit} 對應的 release tag（可能不是每個 commit 都有 release，請改用相近的 tag）。", file=sys.stderr)
        return 1
    rel = _get(f"{API}/releases/tags/{tag}")
    assert isinstance(rel, dict)
    tag_info = _get(f"{API}/commits/{tag}")
    assert isinstance(tag_info, dict)
    commit = str(tag_info["sha"])
    lines = []
    for plat, pattern in PLATFORMS.items():
        asset = next((a for a in rel["assets"] if re.search(pattern, a["name"])), None)
        if asset is None:
            print(f"# {plat}: 這個 release 沒有對應的壓縮檔", file=sys.stderr)
            continue
        digest = str(asset.get("digest") or "")
        sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else sha256_of(asset["browser_download_url"])
        lines.append(f'        RuntimeAsset("{plat}", "{asset["name"]}", {asset["size"]}, "{sha}"),')
    print("LLAMA_CPP = LlamaCppRelease(")
    print(f'    tag="{tag}",')
    print(f'    commit="{commit}",')
    print("    assets=(")
    print("\n".join(lines))
    print("    ),")
    print(")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
