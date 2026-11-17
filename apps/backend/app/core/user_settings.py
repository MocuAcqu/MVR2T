"""使用者在「設定」頁選擇的後端設定（規格 §12.4：推論裝置、記憶體使用偏好），存在 <userData>/settings.json。

只存設定值，不存任何媒體或逐字稿內容（規格 §8.3）。檔案損壞或值不正確時使用預設值。
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Device = Literal["auto", "cpu"]
Memory = Literal["standard", "low"]
FILE = "settings.json"
_lock = threading.Lock()


@dataclass(frozen=True)
class UserSettings:
    #: auto = 依硬體自動選擇（Phase 10）；cpu = 一律用 CPU（例如 GPU 驅動不穩定時）
    device: Device = "auto"
    #: standard = 預設；low = 省記憶體：摘要用較短的 context（4096），語音辨識一次只處理一段
    memory: Memory = "standard"


def load(data_dir: Path) -> UserSettings:
    try:
        raw = json.loads((data_dir / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UserSettings()
    if not isinstance(raw, dict):
        return UserSettings()
    device = raw.get("device") if raw.get("device") in ("auto", "cpu") else "auto"
    memory = raw.get("memory") if raw.get("memory") in ("standard", "low") else "standard"
    return UserSettings(device=device, memory=memory)  # type: ignore[arg-type]


def save(data_dir: Path, value: UserSettings) -> UserSettings:
    with _lock:
        data_dir.mkdir(parents=True, exist_ok=True)
        tmp = data_dir / f"{FILE}.tmp"
        tmp.write_text(json.dumps(asdict(value), indent=2), encoding="utf-8")
        tmp.replace(data_dir / FILE)
    return value
