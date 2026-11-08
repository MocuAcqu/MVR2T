"""長音訊切段（PROJECT_SPEC §9.2）。

要求與做法：
- 保留每段在「原始檔案」中的起訖時間（start / end，秒）。ASR 結果的時間戳記只要加上 start 就能對回原始時間。
- 避免把句子切斷：在目標長度附近的視窗內，優先選擇「最長的靜音」的中點下刀。
- 找不到靜音時才在目標長度硬切，並讓下一段往前重疊 overlap 秒（規格：視模型需求加入適當 Overlap）。
- 切段以 PCM 取樣點為單位，從同一個 16 kHz WAV 精確擷取，不重新編碼，不累積誤差。

plan_segments() 為純函式；write_segments() 只依賴標準函式庫 wave。
"""
from __future__ import annotations

import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Boundary = Literal["silence", "hard", "end"]


@dataclass(frozen=True)
class SegmentParams:
    """預設值以 Qwen3-ASR 的一般用法估計；Phase 05 依實測調整，集中在這裡修改。"""

    target_seconds: float = 30.0  # 每段理想長度
    window_seconds: float = 8.0  # 在 target ± window 內尋找靜音
    min_seconds: float = 5.0  # 每段最短長度（避免切出過短片段）
    overlap_seconds: float = 1.0  # 硬切時與下一段的重疊


@dataclass(frozen=True)
class SegmentPlan:
    index: int
    start: float  # 原始時間軸上的起點（秒）
    end: float  # 原始時間軸上的終點（秒）
    boundary: Boundary  # 這段的「結尾」是怎麼切的

    @property
    def duration(self) -> float:
        return self.end - self.start


def plan_segments(
    duration: float,
    silences: list[tuple[float, float]],
    params: SegmentParams = SegmentParams(),
) -> list[SegmentPlan]:
    if duration <= 0:
        return []
    p = params
    plans: list[SegmentPlan] = []
    pos = 0.0
    # 剩餘長度在 target + window 內就整段收尾，避免最後剩下一小段。
    while duration - pos > p.target_seconds + p.window_seconds:
        ideal = pos + p.target_seconds
        lo, hi = ideal - p.window_seconds, ideal + p.window_seconds
        best: tuple[float, float] | None = None  # (靜音長度, 中點)
        for s, e in silences:
            mid = (s + e) / 2
            if lo <= mid <= hi and mid - pos >= p.min_seconds and duration - mid >= p.min_seconds:
                key = (e - s, -abs(mid - ideal))
                if best is None or key > (best[0], -abs(best[1] - ideal)):
                    best = (e - s, mid)
        if best is not None:
            cut = round(best[1], 3)
            plans.append(SegmentPlan(len(plans), round(pos, 3), cut, "silence"))
            pos = cut
        else:
            cut = round(ideal, 3)
            plans.append(SegmentPlan(len(plans), round(pos, 3), cut, "hard"))
            pos = max(cut - p.overlap_seconds, pos + p.min_seconds)
    plans.append(SegmentPlan(len(plans), round(pos, 3), round(duration, 3), "end"))
    return plans


class Cancelled(Exception):
    pass


def write_segments(
    wav_path: Path,
    plans: list[SegmentPlan],
    out_dir: Path,
    on_progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[Path]:
    """依計畫從 WAV 擷取各段，檔名 seg_0000.wav …；回傳檔案路徑。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with wave.open(str(wav_path), "rb") as src:
        rate = src.getframerate()
        total_frames = src.getnframes()
        params = src.getparams()
        for plan in plans:
            if is_cancelled and is_cancelled():
                raise Cancelled()
            start_f = min(total_frames, round(plan.start * rate))
            end_f = min(total_frames, round(plan.end * rate))
            src.setpos(start_f)
            path = out_dir / f"seg_{plan.index:04d}.wav"
            with wave.open(str(path), "wb") as dst:
                dst.setparams(params)
                remaining = end_f - start_f
                while remaining > 0:
                    chunk = src.readframes(min(remaining, rate * 10))
                    if not chunk:
                        break
                    dst.writeframes(chunk)
                    remaining -= len(chunk) // (params.sampwidth * params.nchannels)
            paths.append(path)
            if on_progress:
                on_progress(plan.index + 1, len(plans))
    return paths
