"""打包檢查（Phase 11）：`mvr2t-backend --self-test` 確認打包後的程式帶齊了所有模組與資料檔。

PyInstaller 只會收進「看得到的 import」；transformers 依模型類型動態載入模組、OpenCC 與 python-docx 需要資料檔，
漏掉時要到使用者實際操作才會出錯。這裡逐項實際執行一次，印出 JSON；全部通過時結束代碼為 0。
已下載模型時（`--models <資料夾>` 或預設的 userData/models），也會實際載入語音辨識的 processor 與模型設定。
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _check(results: dict[str, Any], name: str, fn: Callable[[], Any]) -> None:
    started = time.monotonic()
    try:
        detail = fn()
        results[name] = {"ok": True, "detail": detail, "seconds": round(time.monotonic() - started, 2)}
    except Exception as e:  # noqa: BLE001 - 每一項都要回報，不能中斷
        results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)}


def run_self_test(argv: list[str]) -> int:
    """--models <dir>：指定模型資料夾；--expect-ffmpeg <source>：FFmpeg 必須來自這個來源（例如 bundled）。"""
    # Windows 主控台預設 cp950：改用 UTF-8，JSON 中的中文在 UTF-8 終端機才不會變亂碼
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    from app.core.config import APP_VERSION, Settings

    cfg = Settings()
    expect_ffmpeg = argv[argv.index("--expect-ffmpeg") + 1] if "--expect-ffmpeg" in argv else None
    models = Path(argv[argv.index("--models") + 1]) if "--models" in argv else cfg.models_root
    results: dict[str, Any] = {"version": APP_VERSION, "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0]}

    def fastapi_app() -> str:
        from app.main import create_app

        app = create_app(Settings(auth_token=""))
        return f"{len(app.routes)} routes"

    def opencc_s2twp() -> str:
        from app.engines.asr.text import to_traditional

        out = to_traditional("软件测试与开会")
        assert out == "軟體測試與開會", out
        return out

    def docx_export() -> str:
        import io

        from docx import Document

        d = Document()
        d.add_paragraph("測試")
        buf = io.BytesIO()
        d.save(buf)
        return f"{len(buf.getvalue())} bytes"

    def torch_cpu() -> str:
        import torch

        x = torch.ones(2, 2) @ torch.ones(2, 2)
        assert float(x.sum()) == 8.0
        return f"torch {torch.__version__}, threads {torch.get_num_threads()}"

    def transformers_classes() -> str:
        import transformers
        from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration, Qwen3ASRForTokenClassification  # noqa: F401

        return f"transformers {transformers.__version__}"

    def asr_processor() -> str:
        from app.models.registry import QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B
        from app.models.store import is_installed

        if not is_installed(QWEN3_ASR_0_6B, models):
            return "skipped (model not installed)"
        from transformers import AutoConfig, AutoProcessor

        done = []
        for spec in (QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B):
            if is_installed(spec, models):
                d = str(spec.local_dir(models))
                AutoProcessor.from_pretrained(d, local_files_only=True)
                AutoConfig.from_pretrained(d, local_files_only=True)
                done.append(spec.id)
        return "loaded processor/config: " + ", ".join(done)

    def hardware() -> str:
        from app.core.hardware import detect

        p = detect()
        return f"{p.cpu_name}; RAM {p.ram_total / 1024**3:.1f} GB; GPUs {[g.name for g in p.gpus]}"

    def ffmpeg() -> str:
        from app.engines.media import ffmpeg as ff

        loc = ff.locate_ffmpeg(cfg.ffmpeg_dir, cfg.runtime_ffmpeg_dir, cfg.bundled_ffmpeg_dir)
        if loc is None:
            raise RuntimeError("FFmpeg not found")
        if expect_ffmpeg and loc.source != expect_ffmpeg:
            raise RuntimeError(f"expected FFmpeg source {expect_ffmpeg}, got {loc.source} ({loc.ffmpeg_path})")
        return f"{loc.source}: {ff.ffmpeg_version(loc)}"

    for name, fn in (
        ("fastapi_app", fastapi_app),
        ("opencc_s2twp", opencc_s2twp),
        ("docx_export", docx_export),
        ("torch_cpu", torch_cpu),
        ("transformers_classes", transformers_classes),
        ("asr_processor", asr_processor),
        ("hardware", hardware),
        ("ffmpeg", ffmpeg),
    ):
        _check(results, name, fn)
    ok = all(v["ok"] for v in results.values() if isinstance(v, dict))
    results["ok"] = ok
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    return 0 if ok else 1
