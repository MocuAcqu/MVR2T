# MVR2T - Local Media Studio

> Your Media. Your Machine. Your Knowledge.

本機、離線優先的 AI 影音轉文字與知識整理桌面應用程式。完整規格請見 [`PROJECT_SPEC.md`](./PROJECT_SPEC.md)。

## 目前進度

| Phase | 內容 | 狀態 |
|---|---|---|
| 01 | Project Initialization | ✅ 已在 Windows 驗收 |
| 02 | UI Design System | ✅ 已在 Windows 驗收 |
| 03 | Electron and Backend Integration | ✅ 已在 Windows 驗收 |
| 04 – 12 | 媒體、ASR、LLM、心智圖、Session、Model Manager、硬體偵測、打包 | ⏳ |

## 環境需求

- Node.js 20 以上（建議 22 LTS）
- Python 3.11（後端以 3.11 作為開發與測試基準）
- Windows 10/11 或 macOS

## 第一次設定

**1. 後端虛擬環境**（只需做一次；之後由 Electron 自動啟動後端）

Windows（PowerShell）：

```powershell
cd apps\backend
py -3.11 -m venv .venv          # 若 py -0 找不到 3.11，請先安裝：winget install Python.Python.3.11
.venv\Scripts\Activate.ps1
python --version                # 應顯示 Python 3.11.x
pip install -r requirements/dev.txt
```

macOS（Terminal）：

```bash
cd apps/backend
python3.11 -m venv .venv        # 若找不到指令，請先安裝：brew install python@3.11
source .venv/bin/activate
pip install -r requirements/dev.txt
```

**2. 前端套件**（在專案根目錄）

```bash
npm ci        # 依 package-lock.json 安裝確切版本
```

第一次執行 `npm run dev` 時會下載 Electron 執行檔（約 100 MB）。
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

## Phase 02 驗收清單

- [ ] 首頁顯示產品標語、「新增影音」卡片、AI 模型與這台電腦兩張狀態卡、使用方式四步驟
- [ ] 英文為 Inter、中文為 Noto Sans TC（**拔掉網路後字型仍正常**）
- [ ] 拖曳或選擇 MP4 / MP3 等檔案後，顯示檔名、格式、大小；選 PDF 等不支援格式會出現錯誤訊息
- [ ] 按「開啟工作區」可看到已匯入檔案；重新整理（Ctrl+R）後檔案資訊消失
- [ ] YouTube 輸入框：貼上有效網址顯示「網址格式正確」，亂打文字顯示錯誤
- [ ] 視窗縮到最小（960 x 640）與拉到最大，版面都正常、沒有橫向捲軸
- [ ] 鍵盤 Tab 可以依序走過所有按鈕與輸入框，且看得到黑色焦點環
- [ ] 導覽列切換「首頁 / 工作區 / 模型管理 / 設定」不會出現白畫面
- [ ] 開發模式導覽列有「設計規範」頁，各元件風格一致

## Phase 03 驗收清單

> Windows 上 `.venv\Scripts\python.exe` 是「啟動器」，它會再啟動真正的 Python，
> 所以後端執行時會看到**兩個** `python.exe`（父子關係），這是正常的。
> 可用 PowerShell 查看：
> `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId,ParentProcessId,CommandLine`

- [x] 只執行 `npm run dev`（不手動啟動後端），幾秒內右上角顯示「後端已連線」
- [x] 上面的 PowerShell 指令列出兩個命令列含 `-m app.main` 的 `python.exe`
- [x] 關閉視窗後，兩個 `python.exe` 在幾秒內都消失，且 `npm run dev` **不再顯示** `npm error`
- [x] 在終端機按 Ctrl+C 結束後，兩個 `python.exe` 都消失（Windows 上 Ctrl+C 會強制結束 Electron，後端靠 stdin 偵測自行結束）
- [x] Electron 被強制結束後，兩個 `python.exe` 也會自行結束（以 Ctrl+C 情境驗證）
- [ ] （延後）手動結束 `python.exe` 後畫面顯示「後端意外結束」，按「重新啟動後端」可恢復
- [x] `npm start`（正式版模式）同樣顯示「後端已連線」
- [x] `npm test`、`npm run typecheck`、`pytest` 全數通過

設計規範見 [`docs/DESIGN_SYSTEM.md`](./docs/DESIGN_SYSTEM.md)，開發進度與交接資訊見 [`docs/DEV_LOG.md`](./docs/DEV_LOG.md)。

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

## 已知待辦（刻意留到後續 Phase）

- Phase 04：FFmpeg、媒體匯入 API（後端重新驗證格式與大小）、顯示影音長度
- Phase 11：PyInstaller 打包後端（Electron 已預留 `resources/backend/mvr2t-backend(.exe)` 路徑）
