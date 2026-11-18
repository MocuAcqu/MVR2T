# 開發者說明

[← 回到 README](../README.md)・[進度與驗收紀錄](./PROGRESS.md)・[開發紀錄 DEV_LOG](./DEV_LOG.md)・[規格 PROJECT_SPEC](../PROJECT_SPEC.md)

## 環境需求

- Node.js 20 以上（建議 22 LTS）
- Python 3.11（後端以 3.11 作為開發與測試基準）
- FFmpeg（Phase 04 起；含 ffprobe）
  - Windows：`winget install Gyan.FFmpeg`，裝完**重開終端機與 VS Code** 才會吃到新的 PATH
  - macOS：`brew install ffmpeg`
  - 程式尋找順序：設定指定的資料夾 → 程式資料夾 `runtime\ffmpeg` → 系統 PATH → winget 安裝位置
- Windows 10/11 或 macOS

## 第一次設定

**1. 後端虛擬環境**（只需做一次；之後由 Electron 自動啟動後端）

Windows（PowerShell）：

```powershell
cd apps\backend
py -3.11 -m venv .venv          # 若 py -0 找不到 3.11，請先安裝：winget install Python.Python.3.11
.venv\Scripts\Activate.ps1
python --version                # 應顯示 Python 3.11.x
pip install -r requirements/dev.txt   # Phase 05 起含 PyTorch（CPU 版）與 Transformers，第一次約需數分鐘
```

macOS（Terminal）：

```bash
cd apps/backend
python3.11 -m venv .venv        # 若找不到指令，請先安裝：brew install python@3.11
source .venv/bin/activate
pip install -r requirements/dev.txt
```

**2. 下載 AI 模型**（只需一次，共約 6.2 GB，之後完全離線）

Phase 09 起直接在程式中下載：首頁會提示「還需要下載 AI 模型」，按「全部下載」，或到「模型管理」逐一下載、驗證、刪除。
以下指令留給開發與疑難排解使用（與程式使用相同的位置與驗證方式）：

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m scripts.download_models          # 全部：語音辨識、時間戳記對齊、摘要模型與 llama.cpp
.\.venv\Scripts\python.exe -m scripts.download_models --llm    # 只下載摘要模型（2.6 GB）與 llama.cpp 執行檔（Phase 06）
.\.venv\Scripts\python.exe -m scripts.download_models --list   # 查看安裝狀態與位置
.\.venv\Scripts\python.exe -m scripts.download_models --verify # 重新檢查檔案完整性（SHA-256）
```

模型放在 `%APPDATA%\MVR2T\models\`（macOS：`~/Library/Application Support/MVR2T/models/`），
版本與雜湊固定在 `apps/backend/app/models/registry.py`。下載中斷可重新執行，會從中斷處繼續。
llama.cpp 執行檔（`llama-server`）放在 `%APPDATA%\MVR2T\runtime\llama\`，版本與 SHA-256 固定在
`apps/backend/app/models/runtime.py`（官方 GitHub Release 的 Windows CPU 版，不需要 C++ 編譯器）。

**3. 前端套件**（在專案根目錄）

```bash
npm ci                                   # 依 package-lock.json 安裝確切版本
npm run electron:install -w @mvr2t/desktop   # 補上 Electron 執行檔（見下方說明）
```

`npm ci` 會刪掉整個 node_modules 重新安裝，而 npm 11 預設不執行套件的安裝腳本（allowScripts），所以
`node_modules\electron\dist\electron.exe` 不會出現，`npm run dev` 無法啟動。**每次 `npm ci`／`npm install` 之後執行一次
`npm run electron:install`**（有快取時不必重新下載；`dist:win` 會自動執行）。esbuild 的安裝腳本沒執行不影響使用。
新增 npm 套件時請用 `npx npm@11 install -E -w @mvr2t/desktop <套件>@<版本>`（npm 10 有已知錯誤，見 DEV_LOG）。

## 日常開發

```bash
npm run dev        # 啟動 Vite + Electron；Electron 會自動啟動與關閉後端
npm start          # 以正式版方式執行（打包後的 file:// 頁面 + 正式版 CSP）
npm test           # 前端與 Electron 單元測試（vitest）
npm run typecheck
```

後端測試（PowerShell；Windows PowerShell 5.1 不支援 `&&`，請用 `;`）：

```powershell
cd apps\backend; .\.venv\Scripts\python.exe -m pytest; cd ..\..
```

Phase 03 起**只需要一個終端機**。後端由 Electron 以 `apps/backend/.venv` 的 Python 啟動：

- 連接埠由作業系統動態分配（不再固定 8765），只監聽 127.0.0.1。
- 每次啟動都會產生一次性連線憑證；沒有憑證的請求一律回 401，其他本機網頁無法呼叫後端。
- 關閉視窗 → 後端優雅結束；Electron 當機或被強制結束 → 後端偵測到 stdin 關閉後自行結束，不會殘留。
- 後端無法啟動或意外結束時，首頁「這台電腦」卡片會顯示原因與「重新啟動後端」按鈕。

進階：單獨除錯後端時仍可手動執行 `python -m app.main`（固定 8765、不驗證憑證、開放 http://127.0.0.1:8765/api/docs），
再以環境變數 `MVR2T_BACKEND_URL=http://127.0.0.1:8765` 啟動 `npm run dev`，Electron 就會改連這個後端而不自行啟動。
`MVR2T_PYTHON` 可指定其他 Python 執行檔。

## Phase 11：打包 Windows 安裝程式

使用者決定（2026-11-14）：FFmpeg 內附在安裝程式中（LGPL 版）、只為目前使用者安裝（不需系統管理員）、第一版不簽章。

在專案根目錄依序執行（需要網路；第 2、3 步只有更新版本時才需要）：

```powershell
cd apps/backend
.\.venv\Scripts\python.exe -m pip install -r requirements/build.txt   # PyInstaller（只有打包時需要）
.\.venv\Scripts\python.exe -m scripts.ffmpeg_bundle --resolve         # 固定 FFmpeg 版本 → packaging/ffmpeg.json（要 commit）
.\.venv\Scripts\python.exe -m scripts.ffmpeg_bundle                   # 下載、驗證 SHA-256 → apps/desktop/build-resources/ffmpeg/
.\.venv\Scripts\python.exe -m scripts.build_backend                   # PyInstaller → apps/backend/dist/mvr2t-backend/，並執行 --self-test
cd ../..
npm run dist:win -w @mvr2t/desktop                                     # → apps/desktop/release/MVR2T-Setup-<版本>-x64.exe
```

- `npm ci` 不會下載 Electron 執行檔（Electron 44 沒有 postinstall）；`dist:win` 會先執行 `npm run electron:install`（已有快取時不必下載）。

- 後端打包成 `mvr2t-backend.exe`（onedir），放在 `resources/backend/`；不依賴開發者電腦上的 Python。
  `mvr2t-backend.exe --self-test` 會檢查：API、簡轉繁、Word 匯出、PyTorch、Transformers、ASR 處理器（模型已下載時）、硬體偵測、FFmpeg。
- FFmpeg（BtbN 的 win64 **LGPL** 靜態版，n7.1 系列，LGPL-3.0-or-later）放在 `resources/ffmpeg/`，後端的尋找順序：設定 → 內附 → 下載 → PATH → winget。
- 第三方授權：`resources/THIRD_PARTY_NOTICES.md`（FFmpeg 另附 LICENSE.txt 與原始碼位置 SOURCE.txt）。
- 安裝位置：`%LOCALAPPDATA%\Programs\MVR2T`；模型與設定：`%APPDATA%\MVR2T`（解除安裝時**保留**，要完全移除請手動刪除）。
- 安裝檔較大（PyTorch CPU 版約占一半）；AI 模型不包含在安裝檔內，第一次使用時在「模型管理」下載。
- 打包很吃記憶體（PyInstaller self-test 載入 PyTorch、electron-builder 壓縮約 1.2 GB）：**打包前關閉瀏覽器等程式，只在可用記憶體 8 GB 以上時進行**，
  並一次只做一個步驟（打包後端 → 產生安裝檔 → 安裝測試），不要同時開著 `npm run dev` 或正式版。
  （使用者電腦 19.7 GB，打包剛結束時可用記憶體曾降到 0.5 GB，驗收期間黑屏重開機三次。）
- 沒有簽章：第一次執行安裝檔時 Windows SmartScreen 會顯示「Windows 已保護您的電腦」，按「其他資訊 → 仍要執行」。

## macOS（未驗證）

使用者沒有 Mac（2026-11-17）：只準備設定，**沒有實機驗證**，在 Mac 上可能需要調整。不購買簽章。

- 只做 Apple Silicon（arm64）：llama.cpp 固定 `macos-arm64`（Metal）。Intel Mac 尚未提供。
- 不內附 FFmpeg：請先 `brew install ffmpeg`（後端會到 `/opt/homebrew/bin`、`/usr/local/bin` 尋找）。
- 組建（在 Mac 上）：
  ```bash
  cd apps/backend
  python3.11 -m venv .venv && .venv/bin/pip install -r requirements/build.txt
  .venv/bin/python -m scripts.build_backend
  cd ../.. && npm ci && npm run dist:mac -w @mvr2t/desktop   # → apps/desktop/release/MVR2T-0.1.0-arm64.dmg
  ```
- 沒有簽章與公證：第一次開啟會被 Gatekeeper 擋下，請在 Finder 對 MVR2T 按右鍵 →「打開」，或到「系統設定 → 隱私權與安全性」按「強制打開」。
- YouTube 下載元件會下載 `yt-dlp_macos`；JS 執行環境同樣使用 MVR2T 本身（ELECTRON_RUN_AS_NODE）。

## 開發注意事項

- `requirements/*.txt`、`pytest.ini` 等會被 pip / pytest 以「系統編碼」讀取的檔案，**必須只含 ASCII**（註解請用英文）。繁體中文 Windows 的系統編碼是 cp950，讀到 UTF-8 中文會安裝失敗。

## 專案結構

```text
apps/desktop/    Electron + Vite + React + TypeScript
  electron/      main.ts（視窗、IPC、生命週期）、backend.ts（後端行程管理）、
                 security.ts（來源檢查）、preload.ts（安全橋接）
  src/           components / pages / features / stores / services / hooks / types
apps/backend/    Python + FastAPI
  app/           api / core / services / engines(asr, llm, media) / models / schemas / session
shared/          前後端共用的常數與型別
```
