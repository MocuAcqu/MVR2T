"""一次只執行一個 AI 模型工作（PROJECT_SPEC §5.4 依序載入：語音辨識與摘要模型不同時常駐）。"""
from __future__ import annotations

import threading

MODEL_LOCK = threading.Lock()
BUSY_MESSAGE = "另一個 AI 工作（語音辨識或摘要）正在進行，請等它完成後再試。"
