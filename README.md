# MVR2T - Local Media Studio

> Your Media. Your Video. Your Record.

本機、離線優先的 AI 影音轉文字與知識整理桌面應用程式。完整規格請見 [`PROJECT_SPEC.md`](./PROJECT_SPEC.md)。

## 目前進度

| Phase | 內容 | 狀態 |
|---|---|---|
| 01 | Project Initialization | ✅ 已在 Windows 驗收 |
| 02 | UI Design System | ✅ 已在 Windows 驗收 |
| 03 | Electron and Backend Integration | ✅ 已在 Windows 驗收 |
| 04 | Media Processing（FFmpeg、匯入、抽取音訊、切段） | ✅ 已在 Windows 驗收 |
| 05 | ASR Integration（Qwen3-ASR + 時間戳記對齊） | ✅ 已在 Windows 實測 |
| — | 介面更新（吉祥物 Mono、首頁標題、操作引導） | ✅ 已在 Windows 驗收 |
| — | 優化（完成通知、防睡眠、首頁精簡、引導） | ✅ 已在 Windows 驗收 |
| 06 | LLM Integration（llama.cpp + Qwen3.5-4B 摘要） | ✅ 已在 Windows 驗收 |
| 07 | Mind Map（React Flow 心智圖：編輯、拖曳、匯出 PNG／SVG） | 🧪 待 Windows 驗收 |
| 08 – 12 | Session、Model Manager、硬體偵測、打包 | ⏳ |

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

**2. 下載 AI 模型**（只需一次，共約 6 GB，之後完全離線）

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

## Phase 04 驗收清單

先確認 FFmpeg 已安裝：`ffmpeg -version`、`ffprobe -version` 都有輸出。

- [x] 首頁「這台電腦」卡片的 FFmpeg 列顯示「已安裝 x.x」
- [x] 匯入一個 MP4（**檔名含中文與空格**）：出現「正在複製到工作階段」進度條，完成後顯示格式、大小與**長度**
- [x] 匯入時按「取消」可以中止（大檔案比較容易測）
- [ ] 匯入一個改了副檔名的假檔（例如把 .txt 改名成 .mp4）：顯示「檔案可能已損壞」
- [x] 工作區按「抽取音訊」：進度條與「x / y 秒」更新，完成後列出各段的開始 / 結束時間與切點
- [x] 抽取中按「取消」會停止，顯示「已取消」，卡片內可「再試一次」或「換一個檔案」
- [ ] `%APPDATA%\MVR2T\temp\sessions\` 裡只有一個資料夾；重新整理（Ctrl+R）後換成新的資料夾；關閉程式後清空
- [x] `npm test`、`npm run typecheck`、後端 pytest 全數通過（pytest 需已安裝 FFmpeg，否則 FFmpeg 相關測試會顯示 skipped）

## Phase 05 驗收清單

先完成「第一次設定」的第 2 步（下載模型）。

- [ ] 首頁「AI 模型」卡片：Qwen3-ASR 0.6B 與 Qwen3-ForcedAligner 0.6B 顯示「已安裝」，Qwen3-4B 顯示「Phase 6 推出」
- [ ] 匯入一段**中文**錄音或影片 → 工作區「抽取音訊」→「開始語音辨識」：顯示步驟與進度，完成後列出逐字稿
- [ ] 逐字稿是**繁體中文**（台灣用語），每句前面有時間戳記，標記「精確時間」
- [ ] 抽查幾句：時間戳記與原始影音中說那句話的時間相符（可用其他播放器跳到該時間比對）
- [ ] 匯入一段**英文**錄音，語言自動偵測為「英文」
- [ ] 辨識中按「取消」：幾秒內停止，顯示「已取消語音辨識」
- [ ] 辨識一段 **10 分鐘以上**的錄音，程式不會當掉；完成後工作管理員中沒有殘留的 `python.exe`（辨識用的工作程序會自動結束）
- [ ] 執行 `python -m scripts.benchmark_asr <一段錄音>`，把結果貼回 Cowork（決定 float32 / bfloat16 預設值）
- [ ] `npm test`、`npm run typecheck`、後端 pytest 全數通過（真實模型測試需要測試語音，Windows 上會顯示 4 skipped，屬正常）

進階設定（環境變數，啟動 `npm run dev` 前設定）：
- `MVR2T_ASR_DTYPE=bfloat16`：記憶體約減半；在支援 BF16 的 CPU 上也較快（以 benchmark 結果為準）
- `MVR2T_TORCH_THREADS=4`：限制語音辨識使用的 CPU 執行緒數
- `MVR2T_ASR_BATCH=4`：語音辨識一次處理幾段（預設 1 = 逐段）。核心少的電腦可能較快，但記憶體多約 1 GB；記憶體不足時會自動改回逐段
- `MVR2T_MODELS_DIR=D:\MVR2T\models`：把模型放在其他位置（例如 D 槽）；下載腳本與程式都會使用這個位置

## 介面更新驗收清單（Mono、首頁標題、操作引導）

- [ ] 首頁標題「Your ▢」的黑底字每 2 秒在 Media → Video → Record 間切換，下方像素音波會動；補充說明是「把影片與錄音轉成逐字稿、摘要和心智圖」
- [ ] 左上角 MVR2T 旁有 Mono：滑鼠移過去會折耳、張大眼、鼻子聞聞；點一下會 Q 彈一下
- [ ] 匯入檔案時 Mono 在進度條旁跳；匯入完成後「開啟工作區」發光、旁邊有箭頭，下方出現 Mono 對話框
- [ ] 工作區：「影音資訊」和「音訊抽取與切段」兩張卡片等高；「抽取音訊」發光並有對話框
- [ ] 抽取中 Mono 戴耳機、耳朵跟著擺；完成後換「開始語音辨識」發光
- [ ] 辨識載入模型時 Mono 原地跳；辨識中 Mono 捧著小螢幕（播放三角形清楚可見）；完成後 Mono 舉手歡呼並顯示完成說明
- [ ] 對話框按「知道了」只關這一則；按「不再提示」後不再出現，到「設定 → 操作引導」可重新開啟（重開 App 後設定仍保留）
- [ ] Windows「動畫效果」關閉時（設定 → 協助工具 → 視覺效果），Mono 與標題不再動，標題顯示成三行
- [ ] 開發模式「設計規範」頁最下方可看到所有 Mono 動畫

## 優化驗收清單（通知、睡眠、首頁、引導）

- [ ] 首頁只剩標題、新增影音與使用方式；「AI 模型」「這台電腦」兩張卡片在「模型管理」頁
- [ ] 模型或 FFmpeg 缺少、或後端沒啟動時，首頁出現提醒與「前往模型管理」按鈕；一切正常時不出現
- [ ] 開始語音辨識後切到其他程式：完成時右下角跳出「逐字稿完成」通知、工作列圖示閃爍；點通知回到 MVR2T
- [ ] 辨識時留在 MVR2T 畫面：完成時不跳系統通知（Mono 會在畫面上歡呼）
- [ ] 辨識中不要動電腦，讓螢幕自動關閉（不要闔上筆電）幾分鐘後再喚醒：辨識仍在進行或已完成，內容沒有消失；
      終端機有 `[power] keep awake: on` 與 `[backend] [power] system-required request on`，結束後兩者都變成 off
- [ ] 辨識進行中，在系統管理員 PowerShell 執行 `powercfg /requests`：SYSTEM 區段有 python.exe「MVR2T：正在處理影音…」
- [ ] 闔上筆電的測試請用 `npm start`（正式版）；開發模式要測時先執行 `$env:MVR2T_DEV_NO_HMR=1` 再 `npm run dev`
      （否則 Vite 會在喚醒後重新載入整頁，畫面被清空；正式版不會）
- [ ] 引導對話框不再有「知道了／不再提示」；到「設定 → 操作引導」可以關閉或開啟（如果先前按過「不再提示」，請在這裡重新開啟）

程式圖示：改 `apps/desktop/scripts/generate_icons.py` 後執行 `python apps/desktop/scripts/generate_icons.py`（不需要額外套件）。

要改 Mono 的造型：改 `apps/desktop/scripts/generate_mono_sprite.py` 後執行 `python apps/desktop/scripts/generate_mono_sprite.py`。

## Phase 06 驗收清單（摘要）

先完成「第一次設定」第 2 步的 `download_models --llm`。

- [ ] 「模型管理」頁：Qwen3.5-4B Q4_K_M 與 llama.cpp 都顯示「已安裝」
- [ ] 一段**中文**錄音完成語音辨識後，工作區「摘要」卡片可勾選 7 種內容（預設勾選全文摘要、重點整理、關鍵字、行動事項）
- [ ] 按「產生摘要」：先顯示「正在載入摘要模型」，接著「正在產生摘要 ○○」與進度；完成後以分頁顯示各種內容，全部是**繁體中文**
- [ ] 重點、行動事項等項目旁的時間，點一下會捲動到逐字稿中對應的句子並短暫標示
- [ ] 摘要內容與錄音相符，沒有錄音中不存在的人名、數字、日期（請特別看行動事項的負責人與期限）
- [ ] 一段 **20 分鐘以上**的錄音：顯示「正在閱讀逐字稿 第 N / M 段」，完成後摘要涵蓋前後段的內容；程式不會當掉
- [ ] 產生中按「取消」：幾秒內停止；工作管理員中沒有殘留的 `llama-server.exe`
- [ ] 摘要完成後工作管理員中也沒有 `llama-server.exe`（模型用完即關閉，記憶體歸還）
- [ ] 摘要進行中無法開始語音辨識或重新抽取音訊（顯示「另一個 AI 工作…」）
- [ ] 切到其他程式時，摘要完成會跳出「摘要完成」通知
- [ ] `npm test`、`npm run typecheck`、後端 pytest 全數通過；`tests/test_llm_real.py` 在已下載模型時會實際執行（沙盒約 40 分鐘，含心智圖；設定 `MVR2T_SKIP_LLM_REAL=1` 可略過）

進階設定（環境變數）：
- `MVR2T_LLM_CTX=4096`：記憶體不足時降低 context（預設 8192；長逐字稿會切成較多段）
- `MVR2T_LLM_THREADS=8`：限制摘要使用的 CPU 執行緒數（預設由 llama.cpp 自動決定）
- `MVR2T_LLAMA_SERVER=<路徑>`：改用指定的 llama-server 執行檔（例如自行編譯的版本）

## Phase 07 驗收清單（心智圖）

- [ ] 「摘要」卡片多了「心智圖」選項（預設勾選）；產生時會出現「正在產生心智圖」
- [ ] 摘要完成後，下方「心智圖」卡片顯示：黑底的中心主題在中間，主要分支平均分在左右兩側，往外依序是子主題、細節；決定事項或待辦標有黑色「結論」標籤；全部是**繁體中文**
- [ ] 節點上的時間點一下，會捲動到逐字稿中對應的句子
- [ ] 拖曳節點：子節點一起移動；把左邊的主要分支拖到中心右邊，放開後會換到右側
- [ ] 雙擊節點（或選取後按 F2）可以改文字，Enter 確定、Esc 取消；不能存成空白
- [ ] 選取節點後：Tab 新增子節點、Enter 新增同層、Delete 刪除；工具列的按鈕也可以；中心主題不能刪除
- [ ] 節點外側的「−」收合子節點，收合後顯示隱藏的數量；「全部收合／全部展開」正常
- [ ] Ctrl+Z 復原、Ctrl+Shift+Z（或 Ctrl+Y）重做；「重新排列」清除拖曳位置
- [ ] 「放大」讓心智圖佔滿視窗，Esc 或「縮小」回來
- [ ] 「匯出 PNG」「匯出 SVG」跳出另存新檔視窗（預設在「文件」、檔名「<檔名>-心智圖」）；開啟檔案：白底、內容完整、中文正常、含時間標籤、沒有收合按鈕
- [ ] 「重新產生心智圖」先詢問確認；只重新產生心智圖，其他摘要內容不變
- [ ] 換一個檔案或重新語音辨識後，心智圖清空

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

- 逐字稿編輯、依時間戳記播放原始影音：後續 Phase（Transcript Editor）
- Phase 11：PyInstaller 打包後端（Electron 已預留 `resources/backend/mvr2t-backend(.exe)` 路徑）
