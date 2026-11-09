"""量測這台電腦上語音辨識的速度與記憶體（PROJECT_SPEC §16.4：記錄實測基準，不預先承諾速度）。

用法（在 apps/backend，使用 .venv 的 Python；需先執行 scripts.download_models）：
    python -m scripts.benchmark_asr <影音檔>              # 比較 float32 與 bfloat16，取檔案前 60 秒
    python -m scripts.benchmark_asr <影音檔> --seconds 120

每種精度在獨立的子程序中量測，彼此不影響。輸出載入時間、辨識時間、即時倍率（RTF，越小越快；
0.5 = 1 分鐘音訊約 30 秒辨識完）與峰值記憶體，並建議 MVR2T_ASR_DTYPE 的設定。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _child(dtype: str, wav: str) -> None:
    """子程序：載入模型並辨識一次，輸出一行 JSON。"""
    from app.core.config import settings
    from app.core.procmem import peak_rss_mb
    from app.engines.asr.qwen3 import Qwen3Asr, read_wav_16k_mono
    from app.models.registry import QWEN3_ASR_0_6B

    audio = read_wav_16k_mono(Path(wav))
    seconds = len(audio) / 16000
    asr = Qwen3Asr(QWEN3_ASR_0_6B.local_dir(settings.models_root), dtype, settings.torch_threads)
    t = time.perf_counter()
    asr.load()
    load_s = time.perf_counter() - t
    t = time.perf_counter()
    res = asr.transcribe(audio, None, lambda: False)
    asr_s = time.perf_counter() - t
    import torch

    print(json.dumps({
        "dtype": dtype, "audio_s": round(seconds, 1), "load_s": round(load_s, 1), "asr_s": round(asr_s, 1),
        "rtf": round(asr_s / seconds, 2), "peak_mb": round(peak_rss_mb()), "threads": torch.get_num_threads(),
        "language": res.language, "preview": res.text[:40],
    }, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Benchmark Qwen3-ASR on this computer.")
    p.add_argument("media", nargs="?")
    p.add_argument("--seconds", type=float, default=60.0)
    p.add_argument("--child", nargs=2, metavar=("DTYPE", "WAV"), help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.child:
        _child(*args.child)
        return 0
    if not args.media:
        p.error("請指定一個影音檔")

    from app.core.config import settings
    from app.engines.media.ffmpeg import locate_ffmpeg

    loc = locate_ffmpeg(settings.ffmpeg_dir, settings.runtime_ffmpeg_dir)
    if loc is None:
        print("找不到 FFmpeg。", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "bench.wav")
        subprocess.run(
            [str(loc.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", args.media,
             "-t", str(args.seconds), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav],
            check=True, stdin=subprocess.DEVNULL,
        )
        rows = []
        for dtype in ("float32", "bfloat16"):
            print(f"量測 {dtype} …（每種約需音訊長度的 0.3～3 倍時間）", flush=True)
            r = subprocess.run(
                [sys.executable, "-m", "scripts.benchmark_asr", "--child", dtype, wav],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            line = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith("{")), None)
            if r.returncode != 0 or line is None:
                print(f"  {dtype} 失敗：{(r.stderr or r.stdout).strip().splitlines()[-1:]}")
                continue
            row = json.loads(line)
            rows.append(row)
            print(f"  {dtype:9} 載入 {row['load_s']:>5}s  辨識 {row['asr_s']:>6}s  RTF {row['rtf']:<5}  峰值記憶體 {row['peak_mb']:>6} MB"
                  f"  執行緒 {row['threads']}  [{row['language']}] {row['preview']}")
    if len(rows) == 2:
        f32, bf16 = rows
        faster = "bfloat16" if bf16["rtf"] < f32["rtf"] * 0.9 else "float32"
        print(f"\n建議：MVR2T_ASR_DTYPE={faster}"
              f"（bfloat16 速度為 float32 的 {f32['rtf'] / bf16['rtf']:.2f} 倍，記憶體少 {f32['peak_mb'] - bf16['peak_mb']} MB）")
    print("\n請把以上結果貼回給 Cowork，用來決定預設精度（Phase 10 硬體偵測會自動選擇）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
