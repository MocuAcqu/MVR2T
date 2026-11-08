"""下載並驗證 Phase 05 需要的模型（開發用；Phase 09 會改由程式內的模型管理處理）。

用法（在 apps/backend，使用 .venv 的 Python）：
    python -m scripts.download_models            # 下載語音辨識 + 時間戳記對齊模型
    python -m scripts.download_models --verify   # 重新計算雜湊，檢查已安裝的模型是否完整
    python -m scripts.download_models --list     # 顯示模型與安裝位置

模型會放在 <userData>/models/（Windows：%APPDATA%\\MVR2T\\models），與桌面程式使用的位置相同。
可用環境變數 MVR2T_DATA_DIR 指定其他資料夾。下載中斷可重新執行，已完成的檔案不會重下載。
"""
from __future__ import annotations

import argparse
import sys

from app.core.config import settings
from app.models.registry import ALL_MODELS, QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B
from app.models.store import ModelError, download, is_installed, verify_installed

PHASE05_MODELS = (QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B)


def main(argv: list[str] | None = None) -> int:
    # Windows 主控台可能是 cp950；強制以 UTF-8 輸出，避免中文訊息造成 UnicodeEncodeError。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Download and verify MVR2T models.")
    parser.add_argument("--verify", action="store_true", help="re-hash installed models")
    parser.add_argument("--list", action="store_true", help="list models and their location")
    args = parser.parse_args(argv)
    root = settings.models_root

    if args.list:
        print(f"模型資料夾：{root}")
        for m in ALL_MODELS:
            state = "已安裝" if is_installed(m, root) else ("尚未提供" if not m.downloadable else "未安裝")
            size = f"{m.size_bytes / 1024**3:.2f} GB" if m.files else "-"
            print(f"  {m.display_name:28} {m.role:8} {size:>8}  {state}  ({m.repo}@{m.revision[:7] or '-'})")
        return 0

    if args.verify:
        ok = True
        for m in PHASE05_MODELS:
            if not is_installed(m, root):
                print(f"{m.display_name}：未安裝")
                ok = False
                continue
            problems = verify_installed(m, root)
            print(f"{m.display_name}：{'完整' if not problems else '有問題：' + '；'.join(problems)}")
            ok = ok and not problems
        return 0 if ok else 1

    total = sum(m.size_bytes for m in PHASE05_MODELS if not is_installed(m, root))
    print(f"模型資料夾：{root}")
    if total:
        print(f"需要下載約 {total / 1024**3:.1f} GB（只需一次，之後可離線使用）。")
    try:
        for m in PHASE05_MODELS:
            print(f"{m.display_name}（{m.repo}，{m.license}）")
            download(m, root)
    except ModelError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中斷。重新執行即可從中斷處繼續。", file=sys.stderr)
        return 130
    print("全部完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
