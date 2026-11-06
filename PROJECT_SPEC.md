# MVR2T - Local Media Studio
## PROJECT_SPEC.md

> Version: 2.0  
> Product Type: Cross-platform Local-first AI Desktop Application  
> Target OS: Windows 10/11 + macOS  
> Primary Hardware Target: 16GB RAM  
> AI Strategy: Local Inference + GPU Acceleration When Available + CPU Fallback  
> Network Strategy: Download Models Once, Then Operate Offline

---

# 1. Project Overview

## 1.1 Product Positioning

MVR2T - Local Media Studio 是一套跨平台、本機運算、離線優先的 AI 影音轉文字與知識整理工具。

使用者可以匯入影片、錄音或其他影音檔案，透過本機 AI 模型完成語音辨識、逐字稿生成、摘要、重點整理及心智圖視覺化。

本產品以桌面應用程式形式提供，未來可打包成 Windows 與 macOS 安裝檔，讓其他使用者下載並在自己的電腦執行。

核心原則：

1. Local-first：所有核心 AI 推論都在使用者自己的電腦執行。
2. Offline-first：首次下載模型與必要資源後，核心功能不再依賴網路。
3. Free to use：不依賴付費 API、雲端 GPU 或訂閱服務。
4. Privacy-oriented：使用者的影音與逐字稿不會自動上傳雲端。
5. Session-based：不保存過往處理紀錄，重新整理或結束工作階段後清除未匯出的資料。
6. Cross-platform：支援 Windows 與 macOS。
7. Hardware-adaptive：依照使用者硬體選擇 GPU 或 CPU 推論方式。

## 1.2 Target Users

- 學生：整理課堂錄影、演講、訪談及學習資料。
- 研究者：整理訪談錄音、研究討論及學術演講。
- 一般使用者：將影片或錄音轉換為可閱讀、搜尋及整理的文字。
- 內容創作者：將影音素材轉換成逐字稿、摘要及重點架構。

## 1.3 Core Workflow

影音匯入 → 音訊抽取 → AI 語音辨識 → 逐字稿編輯 → AI 摘要 → 心智圖 → 匯出成果

---

# 2. Product Requirements

## 2.1 Core Features

### A. Media Import

支援使用者匯入本機檔案。

影片格式：
- MP4
- MOV
- MKV
- WEBM

音訊格式：
- MP3
- WAV
- M4A
- FLAC
- AAC
- OGG

功能：
- 拖曳匯入。
- 檔案選擇器。
- 顯示檔案名稱、格式、大小及長度。
- 顯示音訊抽取進度。
- 檢查檔案是否損壞。
- 支援取消處理。

### B. YouTube URL Import

第一版提供有限度的線上輔助功能：

- 輸入 YouTube URL。
- 驗證網址格式。
- 顯示影片 Embed 預覽。
- 嘗試取得使用者有權存取的官方字幕。
- 無法取得字幕時，引導使用者匯入合法取得的本機影片或音訊。

限制：

- 不將未經授權的影片下載列為預設功能。
- 不保證所有公開 YouTube 影片都能取得字幕。
- YouTube 預覽及線上字幕取得需要網路。
- YouTube 功能不應成為核心 AI 工作流程的依賴。

### C. Speech-to-Text

使用本機 ASR 模型將影音轉換成文字。

功能：
- 中文辨識。
- 英文辨識。
- 多語言自動辨識。
- 逐字稿顯示。
- 依照時間戳記分段。
- 支援長音訊分段處理。
- 允許使用者編輯辨識結果。
- 顯示辨識進度。
- 支援取消工作。

輸出：
- Transcript
- Timestamp
- Language
- Segment
- Confidence（僅在模型實際提供時顯示）

### D. Transcript Editor

提供逐字稿編輯介面：

- 顯示時間戳記。
- 顯示每個文字片段。
- 編輯文字。
- 刪除片段。
- 合併片段。
- 匯出字幕。
- 依時間戳記定位原始影音（影音仍在本次 Session 中時）。

### E. AI Summary

使用本機 LLM 產生摘要。

摘要類型：

1. 全文摘要。
2. 重點整理。
3. 條列式筆記。
4. 主題分類。
5. 關鍵字。
6. 行動事項。
7. 問題與結論。

摘要要求：
- 使用繁體中文作為預設輸出語言。
- 保留專有名詞。
- 避免自行補充逐字稿中不存在的事實。
- 重要結論應盡可能連結原始時間戳記。
- 支援長逐字稿的分段摘要與階層式整合。

### F. Mind Map

將摘要與逐字稿整理成心智圖。

使用 React Flow 呈現。

節點類型：
- Central Topic
- Main Topic
- Subtopic
- Detail
- Conclusion

功能：
- 節點拖曳。
- 節點展開與收合。
- 編輯節點文字。
- 新增與刪除節點。
- 依照時間戳記連結逐字稿。
- 匯出 PNG / SVG。

AI 輸出必須先通過 JSON Schema 驗證，避免無效資料造成畫面錯誤。

### G. Export

支援匯出：

| 格式 | 用途 |
|---|---|
| TXT | 純文字逐字稿 |
| SRT | 字幕 |
| VTT | Web 字幕 |
| JSON | 結構化逐字稿與時間戳記 |
| Markdown | 摘要與筆記 |
| PNG | 心智圖圖片 |
| SVG | 心智圖向量圖 |

匯出檔案由使用者自行選擇保存位置。

---

# 3. System Architecture

## 3.1 Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| Desktop | Electron | 桌面視窗、系統整合 |
| Frontend | Vite + React + TypeScript | UI 與互動 |
| UI | Tailwind CSS + shadcn/ui | 視覺元件 |
| State | Zustand | Session 狀態管理 |
| Mind Map | React Flow | 心智圖 |
| Backend | Python + FastAPI | 本機 API |
| Media | FFmpeg | 影音處理 |
| ASR | Qwen3-ASR | 語音辨識 |
| LLM | Qwen3-4B GGUF | 摘要與心智圖資料 |
| Inference | llama.cpp | LLM 本機推論 |
| Python Packaging | PyInstaller | Python Backend 打包 |
| Desktop Packaging | electron-builder | Windows / macOS 安裝檔 |

## 3.2 Architecture Diagram

```text
MVR2T - Local Media Studio
│
├── Electron Desktop
│   │
│   ├── Main Process
│   │   ├── Window Management
│   │   ├── File System Access
│   │   ├── Backend Lifecycle
│   │   └── App Lifecycle
│   │
│   ├── Preload
│   │   └── Secure IPC Bridge
│   │
│   └── Renderer
│       ├── React
│       ├── Vite
│       ├── TypeScript
│       ├── Tailwind
│       ├── Zustand
│       └── React Flow
│
├── Python Backend
│   │
│   ├── FastAPI
│   │
│   ├── Media Engine
│   │   └── FFmpeg
│   │
│   ├── ASR Engine
│   │   └── Qwen3-ASR
│   │
│   ├── LLM Engine
│   │   └── llama.cpp
│   │
│   ├── Summary Engine
│   │
│   ├── Mind Map Engine
│   │
│   └── Export Engine
│
├── Local AI Runtime
│   ├── ASR Model
│   └── LLM Model
│
└── Local Storage
    ├── Models
    ├── Runtime Dependencies
    ├── Config
    └── Temporary Session
```

## 3.3 Communication

Electron Main Process 負責啟動 Python Backend。

Renderer 不應直接操作作業系統檔案或任意呼叫 Node.js API。

建議使用：

- Electron IPC：Renderer 與 Main Process 溝通。
- FastAPI：AI 工作與影音處理 API。
- HTTP localhost：Renderer 與 Backend 溝通。
- SSE 或 WebSocket：傳遞任務進度。

Backend 僅監聽 `127.0.0.1`，不得預設監聽 `0.0.0.0`。

使用一次性本機連線憑證，避免其他本機網頁任意呼叫後端服務。

---

# 4. Hardware Requirements

## 4.1 Primary Development Target

本專案以 16GB RAM 作為主要開發與測試基準。

目標不是保證所有電腦都能即時處理大型影音，而是確保一般 16GB RAM 電腦能夠透過合理的模型選擇與記憶體管理完成主要工作流程。

## 4.2 Recommended Hardware

| Component | Recommended |
|---|---|
| RAM | 16GB |
| Storage | SSD |
| Free Disk Space | 建議至少 15–20GB |
| CPU | 近代 4 核心以上處理器 |
| GPU | 非必要；有支援的 GPU 可加速 |
| Internet | 首次下載模型時需要 |

以上為產品設計目標，不是模型官方公布的最低硬體規格。實際速度與記憶體需求必須透過測試建立。

## 4.3 Hardware Profiles

### Profile A — Minimum Usable

- 8GB RAM。
- CPU 推論。
- 使用較小模型或限制 Context。
- 支援基本影音轉錄與摘要，但處理速度可能較慢。
- 不保證所有長影片都能順利處理。

### Profile B — Standard (Primary Target)

- 16GB RAM。
- CPU 或相容 GPU。
- 預設 ASR：Qwen3-ASR-0.6B。
- 預設 LLM：Qwen3-4B-GGUF Q4_K_M。
- 模型依序載入。
- 以分段摘要處理長逐字稿。

### Profile C — Enhanced

- 32GB RAM 或以上。
- 可選擇更高精度量化模型或較大的 ASR 模型。
- 可使用較長 Context。
- 支援更長影音及較大的工作負載。

---

# 5. AI Model Strategy

## 5.1 ASR Model

### Primary Model

Model ID:

`Qwen/Qwen3-ASR-0.6B-hf`

用途：
- 中文語音辨識。
- 英文語音辨識。
- 多語言語音辨識。
- 長音訊轉錄。
- 語言識別。
- 時間戳記相關工作流程。

優先測試官方 Transformers Backend。

官方原始模型候選：

`Qwen/Qwen3-ASR-0.6B`

可透過官方 `qwen-asr` 套件進行載入。

### Why 0.6B?

以 16GB RAM 為主要硬體基準，0.6B 作為第一版 ASR 模型較容易控制記憶體使用。

1. 避免一開始就採用較大的 1.7B 模型。
2. 降低一般 CPU 使用者的負擔。
3. 保留後續升級模型的彈性。
4. 適合先建立跨平台的可用基準。

### Optional Upgrade

`Qwen/Qwen3-ASR-1.7B-hf`

僅在硬體資源足夠時提供選用。

不可直接假設 1.7B 在所有 16GB RAM 電腦上都能流暢執行。

## 5.2 Timestamp Strategy

Qwen3-ASR 支援語音辨識與時間戳記相關功能。

第一版先使用 ASR 本身可提供的時間資訊。

進階功能可加入：

`Qwen/Qwen3-ForcedAligner-0.6B-hf`

用途：
- 將已有逐字稿與音訊進行對齊。
- 產生字詞或字元層級時間戳記。
- 提升字幕時間精度。

ForcedAligner 不應在第一版預設常駐載入。

若需要執行 Forced Alignment，應在 ASR 完成並釋放主要模型後再載入。

## 5.3 LLM Model

### Primary Model

Model ID:

`Qwen/Qwen3-4B-GGUF`

Default Quantization:

`Q4_K_M`

Official Model File:

`Qwen3-4B-Q4_K_M.gguf`

模型檔案約 2.5GB。

Inference Runtime:

`llama.cpp`

用途：
- 逐字稿摘要。
- 主題分類。
- 重點整理。
- 關鍵字擷取。
- 心智圖 JSON 生成。
- 繁體中文輸出。

### Why Qwen3-4B Q4_K_M?

1. 模型規模適合本專案 16GB RAM 的開發目標。
2. Q4_K_M 可在模型大小與品質之間取得平衡。
3. GGUF 可透過 llama.cpp 執行。
4. llama.cpp 支援 CPU、CUDA 與 Metal 等不同運算後端。
5. 可以降低對特定 GPU 廠牌的依賴。

注意：

模型檔案大小不等於完整推論記憶體需求。實際使用還需要 Context、KV Cache、Runtime Buffer 與作業系統本身的記憶體。

### Context Strategy

不要直接使用模型最大 Context。

第一版建議：

- 預設 Context：4096–8192 tokens。
- 依可用記憶體動態調整。
- 長逐字稿採階層式摘要。
- 避免將整部長影片的逐字稿一次塞入模型。

## 5.4 Model Loading Strategy

必須採用 Sequential Model Loading。

```text
Start
  |
  v
Load ASR Model
  |
  v
Extract Audio
  |
  v
Speech Recognition
  |
  v
Save Transcript in Session
  |
  v
Unload ASR Model
  |
  v
Release Memory
  |
  v
Load LLM Model
  |
  v
Generate Summary
  |
  v
Generate Mind Map JSON
  |
  v
Unload LLM Model
  |
  v
Export
```

原則：

- ASR 與 LLM 不應預設同時常駐。
- 任務結束後釋放模型。
- GPU 記憶體不足時應降低 GPU Offload Layer 數量。
- 記憶體不足時降低 Context 或改用 CPU。
- 若仍無法載入，提供清楚錯誤訊息，不可直接崩潰。

## 5.5 Long Transcript Strategy

長逐字稿必須採用階層式摘要。

```text
Full Transcript
      |
      v
Split into Chunks
      |
      v
Summarize Each Chunk
      |
      v
Collect Intermediate Summaries
      |
      v
Merge and Reorganize
      |
      v
Final Summary
      |
      v
Generate Mind Map
```

切段時必須保留原始時間戳記。

摘要與心智圖節點應盡可能保留來源片段的時間範圍。

---

# 6. GPU Detection and Runtime

## 6.1 General Principle

自動偵測 GPU，並依照模型及 Runtime 的實際支援情況選擇運算裝置。

不得只依據「電腦有 GPU」就判斷 AI 可以使用 GPU。

必須確認：
- GPU 型號。
- 可用 VRAM 或統一記憶體。
- Runtime 是否支援該 GPU。
- CUDA、Metal 或其他必要元件是否可用。
- 模型是否能在該 Backend 正常載入。

## 6.2 Windows

優先測試：

- NVIDIA GPU。
- CUDA Backend。
- llama.cpp CUDA Build。
- PyTorch CUDA。

沒有可用 CUDA 時：

- 使用 CPU。
- llama.cpp CPU Backend。
- ASR 使用經驗證的 CPU 推論路線。

Windows 第一版不承諾 AMD GPU 或 Intel GPU 的所有加速方案。

## 6.3 macOS

Apple Silicon：

- 優先測試 Metal。
- llama.cpp Metal Backend。
- ASR 測試 PyTorch MPS 相容性。
- 不支援時改用 CPU。

Intel Mac：

- 第一版以 CPU 推論為主。
- 不承諾 Intel GPU 可加速所有 AI 模型。

注意：llama.cpp Metal 支援不代表 Qwen3-ASR 的 PyTorch MPS 路線也一定能正常運作。兩者必須獨立測試。

## 6.4 Runtime Selection

建議建立統一的 Hardware Profile：

```json
{
  "platform": "windows",
  "architecture": "x64",
  "ram_total_gb": 16,
  "ram_available_gb": 10,
  "gpu": {
    "vendor": "NVIDIA",
    "name": "Example GPU",
    "vram_gb": 8,
    "cuda_available": true,
    "metal_available": false
  },
  "recommended_device": "cuda",
  "recommended_asr_model": "Qwen3-ASR-0.6B",
  "recommended_llm_model": "Qwen3-4B-Q4_K_M"
}
```

以上僅為資料結構範例，實際硬體資訊必須由偵測程序取得。

---

# 7. Model Manager

## 7.1 Responsibilities

建立獨立的 Model Manager。

功能：
- 列出可用模型。
- 顯示模型用途。
- 顯示模型大小。
- 顯示建議硬體需求。
- 下載模型。
- 顯示下載進度。
- 支援下載取消。
- 驗證檔案完整性。
- 檢查模型版本。
- 刪除模型。
- 顯示模型是否已安裝。
- 離線載入模型。

## 7.2 Download Policy

首次啟動時：

1. 偵測作業系統與硬體。
2. 推薦合適模型。
3. 使用者確認下載。
4. 下載模型權重及必要設定檔。
5. 驗證 SHA-256 或官方提供的完整性資訊。
6. 測試模型載入。
7. 設定模型為可離線使用。

所有下載完成後，核心 AI 功能不得再依賴網路。

## 7.3 Storage

模型應放在使用者的 Application Data 目錄，不應放在安裝程式資料夾。

建議透過 Electron `app.getPath('userData')` 管理應用程式資料目錄。

範例：

```text
ApplicationData/
└── LocalAIStudio/
    ├── models/
    │   ├── asr/
    │   │   └── qwen3-asr-0.6b/
    │   │
    │   └── llm/
    │       └── qwen3-4b-q4_k_m/
    │
    ├── runtime/
    │   ├── ffmpeg/
    │   ├── llama/
    │   └── backend/
    │
    ├── config/
    │   └── app-settings.json
    │
    └── temp/
        └── current-session/
```

---

# 8. Session and Data Management

## 8.1 No Database

第一版不使用 MongoDB、PostgreSQL 或 SQLite。

原因：
- 不需要使用者帳號。
- 不需要跨裝置同步。
- 不保存歷史轉錄。
- 不需要管理多個長期專案。
- 所有處理內容只存在單次 Session。

未來若新增專案保存功能，再評估 SQLite 或其他資料庫。

## 8.2 Session Lifecycle

所有影音、逐字稿、摘要及心智圖資料都屬於單次 Session。

```text
Create Session
     |
     v
Import Media
     |
     v
Process Media
     |
     v
Transcript
     |
     v
Summary
     |
     v
Mind Map
     |
     v
Export
     |
     v
End Session
     |
     v
Clear Temporary Data
```

## 8.3 Persistence Rules

| Data | Persistence |
|---|---|
| AI Model Files | Persistent |
| Runtime Dependencies | Persistent |
| App Settings | Persistent |
| Exported Files | User-controlled |
| Transcript | Session only |
| Summary | Session only |
| Mind Map | Session only |
| Original Media Copy | Session only |
| Extracted Audio | Session only |

前端不得將逐字稿、摘要或心智圖存入 localStorage、sessionStorage 或 IndexedDB。

重新整理頁面後，本次 Session 資料必須清空。

後端必須同步處理 Session 取消與暫存清理。

## 8.4 Crash Recovery

若程式意外關閉：

- 下次啟動時掃描殘留 Session。
- 清除過期暫存檔。
- 不自動恢復未匯出的逐字稿。
- 不刪除使用者已匯出的成果。
- 不刪除已下載的模型。

---

# 9. Media Processing

## 9.1 FFmpeg

使用 FFmpeg 處理影音檔案。

主要工作：
- 影片抽取音訊。
- 音訊格式轉換。
- 音訊重新取樣。
- 音訊聲道轉換。
- 長音訊切段。
- 取得影音長度。
- 取得必要 Metadata。

建議標準化輸入：

- Sample Rate：16000 Hz。
- Channel：Mono。
- Format：WAV。
- Sample Format：依 ASR 模型要求設定。

不得假設所有模型都只能接受相同音訊格式，應以模型官方輸入規格為準。

## 9.2 Long Audio Processing

長影音必須採用切段策略。

要求：
- 保留每個 Segment 的原始起始時間。
- 合併結果時修正時間偏移。
- 避免切段造成句子中斷。
- 視模型需求加入適當 Overlap。
- 支援取消。
- 顯示整體與單段進度。

---

# 10. Backend API

建議 API：

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/health | Backend 狀態 |
| GET | /api/system/info | 硬體資訊 |
| GET | /api/models | 模型清單 |
| POST | /api/models/download | 下載模型 |
| DELETE | /api/models/{model_id} | 刪除模型 |
| POST | /api/session | 建立 Session |
| DELETE | /api/session/{session_id} | 結束 Session |
| POST | /api/media/upload | 匯入媒體 |
| POST | /api/media/extract-audio | 抽取音訊 |
| POST | /api/asr/transcribe | 語音辨識 |
| POST | /api/transcript/update | 編輯逐字稿 |
| POST | /api/summary/generate | 生成摘要 |
| POST | /api/mindmap/generate | 生成心智圖 |
| POST | /api/export | 匯出檔案 |
| GET | /api/tasks/{task_id} | 查詢任務狀態 |
| POST | /api/tasks/{task_id}/cancel | 取消任務 |

所有工作 API 都必須帶有 Session ID。

長時間工作使用 Task ID 追蹤進度。

進度回報可採 SSE 或 WebSocket。

任務取消後應停止相應工作程序，並清理不再需要的暫存資料。

---

# 11. Security and Privacy

1. 所有核心 AI 推論都在本機完成。
2. 不上傳使用者影音或逐字稿。
3. 不需要登入。
4. 不需要第三方 API Key。
5. Backend 預設只監聽 127.0.0.1。
6. Electron 啟用 contextIsolation。
7. Renderer 不直接取得 Node.js 權限。
8. 透過 Preload 暴露有限的 IPC API。
9. 檔案匯入需驗證檔案格式與大小。
10. 避免將使用者檔案路徑直接拼接成任意系統指令。
11. FFmpeg 執行時使用安全的參數陣列，不使用不安全的 Shell 字串串接。
12. 暫存檔案在 Session 結束後清除。

---

# 12. UI / UX Design System

## 12.1 Design Reference

Design Direction:

Uber Design MD

Reference:
- https://github.com/voltagent/awesome-design-md
- https://getdesign.md/uber/design-md

Design Keywords:

- Bold
- Black and White
- Tight Typography
- Urban Energy
- Minimal
- Functional
- Strong Contrast

## 12.2 Visual Principles

1. 黑白為主要視覺。
2. 大標題與清楚的資訊層級。
3. 避免不必要的裝飾。
4. 以留白建立版面節奏。
5. 重要操作使用高對比度。
6. 保持功能性與可讀性。
7. 支援 Desktop 與不同視窗尺寸。

## 12.3 Typography

- English：Inter。
- Traditional Chinese：Noto Sans TC。

## 12.4 Main Pages

### Dashboard

- 品牌名稱。
- 新增影音。
- 匯入本機檔案。
- YouTube URL 輸入。
- 模型狀態。
- 硬體狀態。
- 操作說明。

不需要顯示歷史紀錄或過往專案。

### Media Workspace

- 影音資訊。
- 播放器。
- 處理進度。
- 逐字稿。
- 摘要。
- 心智圖。
- 匯出。

### Model Manager

- 模型清單。
- 下載進度。
- 安裝狀態。
- 硬體相容性。
- 模型刪除。
- 離線狀態。

### Settings

- 語言。
- 預設模型。
- 推論裝置。
- 記憶體使用偏好。
- 暫存清理。
- 關於。

---

# 13. Packaging and Distribution

## 13.1 Packaging Strategy

採用：

- Electron。
- electron-builder。
- Python Backend。
- PyInstaller `onedir`。
- 獨立模型下載器。

不要將所有模型權重直接放進安裝檔。

## 13.2 Windows

Output:

`.exe`

Target:

Windows 10/11 x64。

Backend：

Windows 專用 PyInstaller Build。

GPU Runtime：

- CUDA Build（適用於支援的 NVIDIA GPU）。
- CPU Build 作為備援。

## 13.3 macOS

Output:

`.dmg`

第一版建議分開提供：

- macOS Intel x64。
- macOS Apple Silicon arm64。

Backend：

必須在 macOS 對應環境建置。

GPU Runtime：

- Apple Silicon 優先測試 Metal。
- Intel Mac 以 CPU 為主要支援路線。

正式發行時評估 Developer ID Code Signing 與 Apple Notarization。

## 13.4 Build Pipeline

```text
Source Code
    |
    v
Build React Frontend
    |
    v
Build Electron Main Process
    |
    v
Package Python Backend
    |
    v
Include FFmpeg and Runtime
    |
    v
Electron Builder
    |
    v
Windows Installer / macOS DMG
```

Windows 與 macOS 必須在對應作業系統環境建置。

建議後續使用 GitHub Actions 建立 CI/CD。

## 13.5 First Launch

```text
Install App
    |
    v
Launch App
    |
    v
Detect Hardware
    |
    v
Recommend Models
    |
    v
Download Models
    |
    v
Verify Integrity
    |
    v
Test Model Loading
    |
    v
Ready for Offline Use
```

使用者完成首次設定後，即可在無網路環境執行核心功能。

---

# 14. Project Structure

```text
local-ai-media-studio/
│
├── apps/
│   ├── desktop/
│   │   ├── electron/
│   │   │   ├── main.ts
│   │   │   └── preload.ts
│   │   │
│   │   ├── src/
│   │   │   ├── components/
│   │   │   ├── pages/
│   │   │   ├── features/
│   │   │   ├── stores/
│   │   │   ├── services/
│   │   │   ├── hooks/
│   │   │   └── types/
│   │   │
│   │   └── package.json
│   │
│   └── backend/
│       ├── app/
│       │   ├── api/
│       │   ├── core/
│       │   ├── services/
│       │   ├── engines/
│       │   │   ├── asr/
│       │   │   ├── llm/
│       │   │   └── media/
│       │   │
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── session/
│       │   └── main.py
│       │
│       ├── scripts/
│       ├── requirements/
│       └── pyinstaller.spec
│
├── shared/
│   ├── types/
│   └── constants/
│
├── resources/
│   ├── icons/
│   └── licenses/
│
├── build/
│   ├── windows/
│   └── macos/
│
├── docs/
│
├── package.json
└── PROJECT_SPEC.md
```

---

# 15. Development Roadmap

採用階段式開發，每階段完成驗收後再進入下一階段。

## Phase 01 — Project Initialization

- 建立 Git Repository。
- 初始化 Vite + React + TypeScript。
- 初始化 Electron。
- 建立 Python Backend。
- 確認桌面視窗可啟動。

Acceptance:
- Electron 可以正常開啟前端。
- 前端可以連線至本機 Backend。

## Phase 02 — UI Design System

- 建立 Uber 黑白視覺規範。
- 建立 Typography。
- 建立 Buttons、Inputs、Cards。
- 建立 Dashboard。
- 建立 Responsive Layout。

Acceptance:
- UI 風格一致。
- 桌面視窗尺寸變動時畫面正常。

## Phase 03 — Electron and Backend Integration

- Electron 啟動 Python Backend。
- 建立健康檢查 API。
- 建立安全 IPC。
- Backend Process Lifecycle。
- 程式關閉時停止 Backend。

Acceptance:
- 使用者啟動桌面程式時，Backend 自動啟動。
- 關閉桌面程式時，Backend 正常結束。

## Phase 04 — Media Processing

- 安裝 FFmpeg。
- 匯入影片。
- 匯入音訊。
- 抽取音訊。
- 長音訊切段。
- 顯示進度。

Acceptance:
- 可成功處理指定格式的測試檔案。
- 不同音訊長度都能正確保留時間偏移。

## Phase 05 — ASR Integration

- 整合 Qwen3-ASR-0.6B。
- 測試中文。
- 測試英文。
- 測試多語言。
- 測試時間戳記。
- 測試 CPU 推論。
- 測試 GPU 推論。

Acceptance:
- 逐字稿可以正確顯示。
- 時間戳記可以對應原始音訊。
- 支援取消工作。
- 不因長音訊造成程式崩潰。

## Phase 06 — LLM Integration

- 整合 llama.cpp。
- 載入 Qwen3-4B Q4_K_M。
- 測試繁體中文摘要。
- 測試重點整理。
- 測試 JSON 結構輸出。
- 測試長逐字稿階層式摘要。

Acceptance:
- 能在本機完成摘要。
- 不需要雲端 API。
- 長逐字稿不會一次佔用過多記憶體。

## Phase 07 — Mind Map

- 建立 React Flow。
- 定義節點資料結構。
- 整合 AI JSON。
- 建立節點編輯。
- 建立節點展開與收合。
- 建立 PNG / SVG 匯出。

Acceptance:
- AI 可以產生有效心智圖資料。
- 使用者能編輯節點。

## Phase 08 — Session and Export

- 建立 Session 管理。
- 建立暫存目錄。
- 實作 TXT / SRT / VTT / JSON / Markdown 匯出。
- 實作 Session 清除。
- 實作重新整理清除狀態。
- 實作異常關閉後的暫存清理。

Acceptance:
- 未匯出的資料不會在重新整理後恢復。
- 匯出檔案不受 Session 清除影響。

## Phase 09 — Model Manager

- 建立模型清單。
- 實作模型下載。
- 實作下載進度。
- 實作完整性驗證。
- 實作模型刪除。
- 實作離線載入。
- 實作模型版本管理。

Acceptance:
- 模型下載完成後可離線載入。
- 無網路時不會嘗試重新下載已安裝模型。

## Phase 10 — Hardware Detection

- 偵測 CPU。
- 偵測 RAM。
- 偵測 GPU。
- 偵測 VRAM。
- 偵測 CUDA。
- 偵測 Metal。
- 建立 Runtime Selector。
- 建立記憶體不足的降級策略。

Acceptance:
- Windows NVIDIA GPU 可使用經驗證的 CUDA 路線。
- macOS Apple Silicon 可使用經驗證的 Metal 路線。
- 不支援 GPU 時可以使用 CPU。
- Backend 可以回報目前運算裝置。

## Phase 11 — Windows Packaging

- PyInstaller Backend。
- electron-builder。
- Windows Installer。
- 安裝測試。
- 離線測試。
- 不同硬體測試。

Acceptance:
- 可在未安裝開發環境的 Windows 電腦啟動。
- 不依賴開發者電腦的 Python 或 Node.js。

## Phase 12 — macOS Packaging

- macOS Backend Build。
- Apple Silicon 測試。
- Intel Mac 測試。
- DMG Packaging。
- Code Signing。
- Notarization。
- 離線測試。

Acceptance:
- 可在目標 macOS 環境安裝及啟動。
- 模型可正常載入。
- 不依賴開發者電腦的 Python 環境。

---

# 16. Testing Requirements

## 16.1 Functional Testing

- 影片匯入。
- 音訊匯入。
- FFmpeg 抽取。
- 中文辨識。
- 英文辨識。
- 時間戳記。
- 摘要。
- 心智圖。
- 匯出。
- Session 清除。

## 16.2 Hardware Testing

至少測試：

| Test Machine | RAM | GPU |
|---|---:|---|
| Windows CPU | 16GB | 無可用 CUDA |
| Windows NVIDIA | 16GB | NVIDIA GPU |
| Mac Apple Silicon | 16GB | Apple GPU |
| Mac Intel | 16GB | CPU |

另外應使用 8GB RAM 環境測試降級策略。

## 16.3 Offline Testing

測試步驟：

1. 安裝應用程式。
2. 下載模型。
3. 驗證模型。
4. 關閉應用程式。
5. 中斷網路。
6. 重新啟動應用程式。
7. 匯入本機影音。
8. 完成 ASR。
9. 完成摘要。
10. 產生心智圖。
11. 匯出成果。

Acceptance:
核心 AI 工作流程不得要求網路連線。

## 16.4 Performance Testing

需要記錄：

- Model Loading Time。
- Audio Processing Time。
- ASR Processing Time。
- LLM Processing Time。
- Peak RAM Usage。
- Peak VRAM Usage。
- CPU Usage。
- GPU Usage。

測試不同影音長度，例如 5、30、60 分鐘。

不預先承諾固定處理速度，先建立各平台的實測基準。

---

# 17. Licensing and Distribution

正式發行前必須確認：

- ASR 模型授權。
- LLM 模型授權。
- llama.cpp 授權。
- FFmpeg 編譯組態與授權。
- Python 套件授權。
- Electron 與 npm 套件授權。

應將第三方 License 與 Notice 放入安裝程式。

模型權重不應未經確認就重新包裝或再散布。

優先採用官方模型下載來源，並記錄模型版本及檔案雜湊。

---

# 18. Development Rules for Claude Code

Claude Code 必須遵守以下開發原則：

1. 一次只實作一個 Phase。
2. 不得一次生成整個專案所有程式碼。
3. 開發前先檢查目前資料夾與既有程式碼。
4. 不可覆蓋已存在且可正常運作的功能。
5. 每次修改需說明檔案用途。
6. 程式碼需包含適當註解。
7. 前端、Backend、AI Engine 必須維持模組化。
8. 不得把模型權重提交至 Git。
9. 不得將付費 API 或雲端 GPU 作為必要依賴。
10. 不得將逐字稿寫入持久化儲存。
11. 不得假設 GPU 一定可用。
12. 必須提供 CPU Fallback。
13. 必須支援 Windows 與 macOS 的差異化 Runtime。
14. 所有長時間任務必須提供進度及取消機制。
15. 每個 Phase 完成後先執行測試與驗收。
16. 模型 ID、模型版本及下載來源集中管理，不可散落在程式碼中。
17. 模型 Runtime 必須可以替換，不得讓前端直接依賴特定模型。
18. 所有模型下載與執行都必須支援本機路徑。
19. 開發階段使用明確版本的依賴套件，避免未驗證的最新版造成跨平台差異。
20. 發行前執行離線測試與授權檢查。

---

# 19. Final Product Definition

MVR2T - Local Media Studio 最終應具備以下特性：

- Windows 與 macOS 桌面應用程式。
- 本機影音匯入。
- 本機 AI 語音辨識。
- 本機 LLM 摘要。
- AI 心智圖。
- 字幕與筆記匯出。
- GPU 自動偵測。
- CPU Fallback。
- 首次下載模型。
- 後續完全離線使用核心功能。
- 不依賴付費 API。
- 不依賴雲端 GPU。
- 不保存處理歷史。
- 支援一般 16GB RAM 電腦作為主要測試基準。

**Product Philosophy:**

> Your Media. Your Machine. Your Knowledge.
>
> Keep your media local. Turn information into knowledge.