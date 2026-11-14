"""打包後端（Phase 11）：PyInstaller onedir → dist/mvr2t-backend/，接著執行 --self-test 確認模組與資料檔齊全。

用法（在 apps/backend，使用 .venv 的 Python；先 `pip install -r requirements/build.txt`）：
    python -m scripts.build_backend
    python -m scripts.build_backend --skip-test   # 只打包

必須在目標作業系統上建置（Windows 版在 Windows 打包，PROJECT_SPEC §13.2）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DIST = BACKEND / "dist"
OUT = DIST / "mvr2t-backend"


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    started = time.monotonic()
    cmd = [
        sys.executable, "-m", "PyInstaller", str(BACKEND / "packaging" / "mvr2t-backend.spec"),
        "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(BACKEND / "build" / "pyinstaller"),
    ]
    print("執行：" + " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=BACKEND)
    if rc != 0:
        print(f"PyInstaller 失敗（代碼 {rc}）", file=sys.stderr)
        return rc
    exe = OUT / ("mvr2t-backend.exe" if sys.platform == "win32" else "mvr2t-backend")
    print(f"完成：{exe}（{dir_size(OUT) / 1024**2:,.0f} MB，{time.monotonic() - started:.0f} 秒）", flush=True)
    if "--skip-test" in argv:
        return 0
    print("執行 --self-test …", flush=True)
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.call([str(exe), "--self-test"], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
