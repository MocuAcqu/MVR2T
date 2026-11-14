# MVR2T 第三方軟體與授權

MVR2T 在你的電腦上離線執行。以下是安裝程式內附、或第一次使用時下載的第三方軟體與模型。

## 安裝程式內附

| 軟體 | 用途 | 授權 |
|---|---|---|
| Electron（含 Chromium、Node.js） | 桌面程式框架 | MIT（Chromium 各元件依其授權） |
| React、Zustand、React Flow（@xyflow/react）、html-to-image 等前端套件 | 介面 | MIT |
| Inter、Noto Sans TC 字型 | 介面字型 | SIL Open Font License 1.1 |
| Python 3.11 | 本機後端 | PSF License |
| FastAPI、Starlette、Uvicorn、Pydantic | 本機後端 | MIT／BSD |
| PyTorch | 語音辨識推論 | BSD-3-Clause |
| Hugging Face Transformers、Tokenizers、Safetensors | 語音辨識模型載入 | Apache-2.0 |
| NumPy | 數值運算 | BSD-3-Clause |
| OpenCC | 簡體轉繁體（臺灣用語） | Apache-2.0 |
| python-docx、lxml | Word 匯出 | MIT／BSD-3-Clause |
| **FFmpeg**（LGPL 版，`resources/ffmpeg/`） | 讀取影音、抽取音訊 | **LGPL-2.1-or-later**。授權全文：`resources/ffmpeg/LICENSE.txt`；版本與原始碼位置：`resources/ffmpeg/SOURCE.txt`。FFmpeg 以獨立執行檔方式使用，可自行替換為其他相容版本。 |

## 第一次使用時下載（模型管理）

| 項目 | 用途 | 授權 |
|---|---|---|
| Qwen3-ASR 0.6B、Qwen3-ForcedAligner 0.6B（Qwen 官方） | 語音辨識、時間戳記對齊 | Apache-2.0 |
| Qwen3.5-4B Q4_K_M（unsloth 由官方權重量化） | 摘要與心智圖 | Apache-2.0 |
| llama.cpp（官方 GitHub Release；CPU 版，NVIDIA 電腦可另外下載 CUDA 版與 NVIDIA CUDA 執行庫） | 執行摘要模型 | MIT（CUDA 執行庫依 NVIDIA 授權） |

模型與執行檔的版本、來源與 SHA-256 固定在程式中，下載後逐一驗證。
