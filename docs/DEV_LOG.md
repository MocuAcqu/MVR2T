# 開發紀錄（給接手的 Claude / Claude Code）

最後更新：2026-11-11。Phase 06 已驗收；語音辨識批次在使用者電腦沒有效益，預設改回逐段。下一步 Phase 07 心智圖。

## 目前進度

| Phase | 狀態 |
|---|---|
| 01 專案初始化 | ✅ 使用者已在 Windows 驗收通過（Electron 視窗開啟、後端已連線、Python 3.11.6） |
| 02 UI 設計系統 | ✅ 使用者已在 Windows 驗收通過（2026-11-06） |
| 03 Electron 啟動 Python Backend | ✅ 使用者已在 Windows 驗收通過（2026-11-07；手動結束啟動器一項延後，見下方） |
| 依賴升級 | ✅ 使用者已在 Windows 驗收通過（2026-11-07） |
| 04 Media Processing | ✅ Windows 主要項目驗收通過（2026-11-09，見「Windows 套用回饋」） |
| 05 ASR Integration | ✅ Windows 實測通過（24 分鐘中文錄音 → 320 句，float32 約 32 分鐘）；benchmark 待使用者執行 |
| 介面更新（Mono／標題／引導） | ✅ Windows 驗收通過（2026-11-09） |
| 優化（通知／防睡眠／首頁／引導） | ✅ Windows 驗收通過（2026-11-09） |
| 06 LLM Integration | ✅ Windows 驗收通過（2026-11-10，llama.cpp b11312＋Qwen3.5-4B） |

## 沙盒驗證結果（2026-11-06）

環境：Node 22、npm 10、Python 3.11.15（uv）、Electron 33.2.1（Xvfb + `--no-sandbox`，因沙盒以 root 執行）。

- `npm install`：所有固定版本都存在（含 `@fontsource-variable/noto-sans-tc@5.1.0`）。
- `pytest`：16 passed。`npm test`（vitest）：80 passed。`npm run typecheck`、`npm run build`：通過。
- Playwright 截圖（960x640、1280x820）：無橫向捲軸、Inter / Noto Sans TC 實際載入、焦點環可見、
  PDF 被拒、MP4 顯示檔名 / 格式 / 大小、YouTube 驗證訊息、導覽切換、重新整理後 Session 清空、未使用 Web Storage。
- 真實 Electron E2E（正式版 file:// 與開發版 Vite 兩種模式）：
  後端自動啟動於動態埠、無憑證 401、有憑證 200、/api/docs 關閉、Renderer 無 Node 權限、無 CSP 違規、
  CSP 阻擋外部網路、後端被殺 → 顯示錯誤 → 重新啟動成功（新憑證）、關閉視窗 → 後端優雅結束、
  Electron 被 SIGKILL → 後端自行結束、找不到 Python → 清楚錯誤、後端路徑含空格可正常啟動。

### 驗證中發現並修正的問題

1. **Phase 02 typecheck 失敗**：`MediaDropzone.tsx` 有未使用的 `Badge` import（`noUnusedLocals`）。已移除。
2. **Phase 02 導覽切換白畫面（嚴重）**：`AppShell` 的 `useEffect(() => window.scrollTo(0, 0), [page])`
   會把 `scrollTo()` 的回傳值當成 cleanup。新版 Chromium 的 `scrollTo()` 回傳 Promise，React 呼叫它時崩潰
   （`destroy is not a function`），點任何導覽都變白畫面。改為大括號函式本體。
   **規則：effect 一律用大括號，不要用箭頭函式直接回傳運算式。**
3. **Phase 03 開發中發現**：Electron 當機時後端 stdout 也斷了，watchdog 先 `print` 會丟 `BrokenPipeError`，
   導致沒設定 `should_exit`、後端成為孤兒行程。改為先排保險計時器與 `should_exit`，最後才嘗試輸出。
   已加回歸測試 `test_exits_when_parent_dies_and_stdout_is_broken`（並確認舊程式碼會讓它失敗）。

## Windows 驗收回饋與修正（2026-11-07）

使用者在 Windows 回報：dev / start 皆「後端已連線」，npm test 80、pytest 16、typecheck 通過。從輸出發現：

1. **Windows venv 的 python.exe 是啟動器**：Electron spawn 的 PID（啟動器）≠ ready 行的 PID（實際伺服器）。
   優雅結束（stdin EOF）正常；但強制終止原本只 kill 啟動器，可能留下孤兒。
   修正：`killProcessTree()` 在 Windows 使用 `taskkill /pid <pid> /T /F`；`BackendState.pid` 改為 ready 行回報的實際伺服器 PID。
2. **關閉視窗後 `npm run dev` 顯示 npm error**：concurrently `-k` 結束 vite 時 vite 以代碼 1 結束。
   修正：`concurrently -k -s command-electron`，整體結束代碼以 Electron 為準（沙盒驗證 0）。
3. **終端機 Ctrl+C 跳過正常結束流程**：Electron 被 SIGINT 直接結束，不經 before-quit。
   修正：main.ts 監聽 SIGINT / SIGTERM → `app.quit()`（沙盒驗證：stopping → stdin closed → stopped）。

修正後沙盒：vitest 81、Electron E2E 23/23。

補驗（2026-11-07，Windows）：
- 兩個 python.exe（.venv 啟動器 → Python311 實際伺服器）確認存在；Ctrl+C 結束後兩者皆消失。
- **修正 3 在 Windows 透過 npm 啟動時不會生效**：`node_modules/electron/cli.js` 收到 Ctrl+C 後呼叫
  `child.kill('SIGINT')`，在 Windows 等同 TerminateProcess，Electron 主行程來不及執行 before-quit。
  後端仍靠 stdin EOF 自行結束（已在 Windows 證實），所以不再額外處理；Ctrl+C 只是開發情境，正式版沒有終端機。
  修正 3 保留（Linux / macOS 與直接執行 electron.exe 時有效，無副作用）。
- `終止批次工作 (Y/N)?` 亂碼：cmd.exe 的 cp950 提示被 concurrently 以 UTF-8 顯示，無害。

## Phase 03 設計摘要

- `apps/desktop/electron/backend.ts`：`BackendManager`
  - 開發：`apps/backend/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`；`MVR2T_PYTHON` 可覆寫。
  - 正式版（Phase 11）：預留 `resources/backend/mvr2t-backend(.exe)`。
  - `spawn(command, args, { shell: false, windowsHide: true })`：路徑含空格安全。
  - 環境變數：`MVR2T_BACKEND_PORT=0`、`MVR2T_AUTH_TOKEN`（每次啟動 32 bytes 隨機）、`MVR2T_ALLOWED_ORIGINS`、
    `MVR2T_EXIT_ON_STDIN_EOF=1`、`PYTHONUTF8=1`（避免 cp950）。
  - 後端在 stdout 輸出 `MVR2T_BACKEND_READY {"port":…,"pid":…}` → Electron 以憑證輪詢 `/api/health` → `running`。
  - 結束：關閉 stdin → 後端優雅結束；5 秒逾時才 `kill`。`process.on('exit')` 同步 kill 作為最後防線。
- `apps/backend/app/main.py`：自行綁定 socket（port 0 由 OS 分配，無競爭）、stdin watchdog、
  `app/core/security.py` 的 Bearer token middleware（CORS 在最外層，preflight 與 401 都有 CORS 標頭）。
  手動 `python -m app.main` 仍是 Phase 01 的開發模式（8765、無憑證、有 /api/docs）。
- `electron/security.ts`：IPC 只接受本程式頁面主框架（dev server origin 或同一個 dist/index.html）。
  正式版 file:// 頁面的 Origin 為 `null`，後端 CORS 只在 Electron 啟動時允許它（且仍需憑證）。
- CSP：正式版由 `vite.config.mts` 寫入 meta（`script-src 'self'`、`connect-src http://127.0.0.1:*`）；
  開發版由 `main.ts` 以標頭加入（允許 Vite HMR）。
- IPC：`getAppInfo`、`getBackendState`、`restartBackend`、`onBackendState`（Main 推送）。
  `AppInfo.backendUrl` 已移除，改由 `BackendState.url / token` 提供。
- macOS：關閉視窗不結束程式（後端保留），Cmd+Q 才結束 — 依平台慣例。

## 協作流程（2026-11-07 起，重要）

同一份程式碼有兩個 Claude 在改：沙盒的 Cowork Claude（以 zip 交付整個專案）與使用者 VS Code 裡的 Claude Code（直接改本機檔案）。
2026-11-07 使用者以依賴升級 zip 整包覆蓋後，**Claude Code 先前在本機做的修改被蓋掉**（根目錄 `start` 指令、它自己的 test_lifecycle 修法）。
專案原本沒有 Git，所以覆蓋了什麼看不出來。今後規則：

1. 使用者電腦上的專案資料夾以 Git 管理。**套用任何新檔案前先 commit**，套用後用 `git status` / `git diff` 檢查，
   被蓋掉的本機修改可以從前一個 commit 找回。
2. Cowork Claude 交付時只給「有變更的檔案」並列出檔案清單（或整包 zip 加變更清單），不再無說明地整包覆蓋。
3. Claude Code 在本機做的修改，請使用者把 `git diff` 或檔案貼回 Cowork 對話，讓沙盒副本同步。
4. 2026-11-07 已同步：根目錄 `"start": "npm run start -w @mvr2t/desktop"`、README 後端測試改為 PowerShell 寫法（`;` 而非 `&&`）。

## 使用者環境

- Windows、VS Code（已安裝 Claude Code）、PowerShell，繁體中文系統（locale 編碼 cp950）。
- Python 3.11（以 `py -3.11 -m venv .venv` 建立），venv 在 `apps/backend/.venv`。
- **專案路徑含空格**：`C:\Users\User\Desktop\MVR2T AI`。
- Phase 03 起只需 `npm run dev`，不需另開終端機啟動後端。

## 已知教訓

- `requirements/*.txt`、`pytest.ini` 這類會被 pip / pytest 以系統編碼讀取的檔案**只能用 ASCII**。
- 沙盒的 `/bin/sh` 是 dash，不支援 `{a,b}` 大括號展開，寫腳本請用 bash。
- 沙盒內建的 Tailwind 是 v4，專案固定 v3.4；請用專案 node_modules 內的版本。
- `tsc` 只要有選項層級錯誤（例如缺型別套件）就會略過語意檢查，「沒有報錯」不代表通過。
- 沙盒的 init 不會立即回收殭屍行程，`kill -0` 對殭屍也成功；判斷行程是否存活請看 `/proc/<pid>/stat` 狀態不是 `Z`。
- 在沙盒跑 Electron：`xvfb-run -a`，並加 `--no-sandbox`（root）。

## 語音辨識加速（2026-11-10）

### 量測（使用者 Windows，24 分鐘中文錄音，修正 timings 後）
辨識 46:58（含載入，約 1.96 倍音訊長度）、對齊 13:27（約 0.56 倍）→ 辨識佔 78%、對齊 22%。
總時間 1:00:27 比先前同一段錄音（約 32 分鐘）慢近一倍，原因未確認（電源模式、沒插電或過熱降速），使用者將插電、最佳效能後重測。
**決定：不做「辨識與對齊同時進行」**：最多只能省下對齊的 22%，純 CPU 上兩個模型搶同一批核心，實際更少，還要多約 1.7 GB 記憶體。

### 沙盒比較（2 核 CPU，Piper 合成的 5.5 分鐘中文會議，切成 30 秒）
| 做法 | 辨識時間 | 相對 | 文字 | 峰值記憶體 |
|---|---|---|---|---|
| 逐段（原本） | 222.5 s | 1.00× | 基準 | 5.32 GB |
| 2 段一批 | 150.7 s | 1.48× | 完全相同 | 5.32 GB |
| 4 段一批 | 132.4 s | 1.68× | 完全相同 | 5.41 GB |
| 8 段一批 | — | — | — | 超過沙盒 6 GB 被系統終止 |
| int8 動態量化 | — | — | — | torch.ao.quantization 已棄用（需改用 torchao，額外套件），不採用 |

完整流程（含載入與對齊）：逐段 328 s → 4 段一批 249 s（**快 24%**），85 句的文字與時間戳記完全相同；test_asr_real 的 WER 仍為 3.0%。

### 實作
- `Qwen3Asr.transcribe_batch()`：同一次 generate 處理多段；每段各自判斷是否被長度上限截斷（不計 padding）。
- `pipeline.recognize()`：依 `Engines.asr_batch` 分批（設定 `MVR2T_ASR_BATCH`，原預設 4，2026-11-11 改為 1）；進度顯示「第 1–4 / N 段」；
  批次時遇到記憶體不足（MemoryError 或含 memory 的 RuntimeError）→ 改回逐段，之後也不再批次。
- EngineSpec 多了 asr_batch（預設 4），測試與 benchmark 不受影響；新增 tests/test_asr_batch.py。

### Windows 實測（2026-11-11，同一段 23:57 中文錄音，插電、最佳效能；先批次再逐段）
| | 4 段一批 | 逐段（MVR2T_ASR_BATCH=1） |
|---|---|---|
| 辨識 | 35:07 | 26:38 |
| 對齊（不受批次影響） | 12:32 | 9:07 |
| 總計 | 47:39 | 35:47 |
| 辨識 ÷ 對齊 | 2.80 | 2.92 |
| 尖峰工作集 | 約 5.6 GB | 約 4.4 GB |
| 句數 | 321 | 320 |

對齊也慢了 37%，代表第一次整台電腦就比較慢，總時間不能直接比；以對齊為基準換算，批次頂多快約 4%（誤差範圍內），
**沒有重現沙盒的 1.7 倍**（多核 CPU 逐段就能用滿核心），尖峰記憶體反而多約 1.2 GB，文字也不是逐字相同（321 vs 320 句）。
**決定：MVR2T_ASR_BATCH 預設改回 1**，功能保留供核心少的電腦嘗試。同一台電腦每次速度差異很大（46:58／35:07／26:38），
之後評估加速要交替順序、多跑幾次。

### 其他（同一批）
- 同步 Claude Code 本機 8b76c6e：transcribe.py 的步驟耗時 `timings` 被每句時間戳記種類的 set 覆蓋（變數同名），改名 sentence_timing＋測試。
- generate_icons.py 新增 `--check`：比對解碼後的像素。不同 zlib（Python 3.11／3.13）壓縮出的位元組不同，但像素相同，
  所以「可重現」定義為像素相同（Windows 驗收發現）。

## Phase 06 LLM Integration — 實作與驗證（2026-11-09～10）

### 使用者決策
- 執行方式：**官方預先編譯的 llama-server**（獨立程序），不用 llama-cpp-python（Windows 沒有官方 wheel，需 C++ 編譯器）。
- 模型：先比較再決定 → 使用者看過比較後選 **Qwen3.5-4B Q4_K_M**（unsloth/Qwen3.5-4B-GGUF，Apache-2.0）。
  **與規格 §5.3 不同**：規格寫 Qwen/Qwen3-4B-GGUF（Qwen 官方），但 Qwen 官方沒有發布 Qwen3.5 / 2507 的 GGUF，只有第三方量化。
  三個候選都登錄在 registry.LLM_CANDIDATES（含 SHA-256），改預設只要改 LLM_MODEL。
- 摘要內容：**讓使用者勾選**規格 §4-E 的 7 種（預設勾全文摘要、重點整理、關鍵字、行動事項）。
- 先只做 CPU 版（GPU 在 Phase 10）。

### 架構
- `app/engines/llm/server.py`：LlamaServer。摘要時才啟動（隨機埠、127.0.0.1、每次新 API key、`--parallel 1`、
  `--reasoning-budget 0` + `enable_thinking:false` 關閉思考模式、`--cache-ram 0`），用完 terminate；取消 = kill 程序。
  `/health` 503 = 載入中。啟動失敗依 log 給中文原因（記憶體不足、架構不支援、模型損壞）。
- `app/core/childproc.py`：spawn_tied。**後端當機也不留孤兒 llama-server**：Windows 用 Job Object
  （KILL_ON_JOB_CLOSE，handle 只有後端持有），Linux 用 PR_SET_PDEATHSIG（prctl 在父程序準備好，fork 後的子程序不 import 任何東西）。
- `app/engines/llm/summarize.py`：
  - token 估計（中日韓字元各 1、其他 3.2 字元 1，偏保守）；依預算切段，句子不拆。
  - 每種摘要類型一次請求，**輸入放前面、指示放最後**，同一份輸入只算一次（llama-server prompt cache；實測 7 次請求共用 85% prompt）。
  - 回應用 JSON schema 約束（llama.cpp 轉成 grammar），**每個字串都有 maxLength**：沒有上限時分段筆記的 summary
    寫超過 900 tokens 被截斷成無效 JSON（沙盒實測）。最壞情況長度都小於 max_tokens。
  - 時間戳記：模型只引用句子編號 refs，程式驗證後換成時間範圍，模型不會編造時間。
  - 長逐字稿（§5.5）：分段 → 每段筆記（摘要、重點、關鍵字、待辦、問題）→ 筆記太長時兩兩整合，必要時多層 →
    最終每種類型。**整合只濃縮「摘要與重點」，待辦、問題、關鍵字原樣保留到最後**：
    第一版連同待辦一起整合三層後，5 個負責人只剩 3 個（沙盒實測），改版後全部保留。
  - 後處理：OpenCC s2twp 轉繁體；去掉字串尾的 `} }` 殘渣；「空字串／未提及／無」等字樣視為空白（Qwen3-4B 會把「留空」寫成文字）。
  - Budget（8192 context）：每段 3000、筆記 4800、輸出 1600；`MVR2T_LLM_CTX` 較小時等比縮小。
- `app/services/summary.py`＋`app/api/summary.py`：POST /api/summary/generate（types）→ task；GET /api/summary。
  `app/services/model_lock.py` 的 MODEL_LOCK 取代原本的 _transcribe_lock：**語音辨識與摘要不會同時載入模型**（§5.4）；
  摘要中也不能重新抽取音訊。重新辨識／重新抽取會清除摘要。結果存在 Session（記憶體＋summary.json，§8.3）。
- `app/models/runtime.py`：llama.cpp 版本固定（tag、commit、各平台壓縮檔 SHA-256）、下載驗證解壓（防 zip slip）、尋找執行檔；
  `MVR2T_LLAMA_SERVER` 可指定執行檔（沙盒用自行編譯的版本）。
  `scripts/resolve_llama_release.py --commit <sha>`：從 GitHub 查 tag 與 SHA-256，印出可貼到 runtime.py 的設定。
  **沙盒連不到 GitHub（403）**，所以 tag 與 SHA-256 由使用者電腦上的 Claude Code 查出填入。
- 前端：SummaryCard（7 種內容勾選、載入時 Mono 跳、整理時 Mono 捧螢幕、分頁顯示、時間標籤點擊捲動到逐字稿句子）、
  引導新增「summarize」步驟、摘要完成通知、處理中防睡眠、模型管理頁顯示 llama.cpp 狀態。

### Phase 06 模型比較（沙盒，2 核 CPU，llama.cpp 0c1e570 自行編譯）
同一份 8.5 分鐘虛構中文會議（tests/fixtures/meeting_zh.json，有標準答案），7 種摘要一次產生：

| 模型 | 總時間 | 生成 tok/s | 行動事項（5 人） | 備註 |
|---|---|---|---|---|
| Qwen3-4B（Qwen 官方 GGUF） | 20.3 分 | 2.8 | 5/5，另誤列 2 個討論事項；owner 寫「空字串」 | 關鍵字較空泛、重點只有 5 個 |
| Qwen3-4B-Instruct-2507（unsloth） | 24.1 分 | 2.7 | 5/5 | 內容最詳細，全文摘要偏長（約 430 字） |
| Qwen3.5-4B（unsloth） | 15.2 分 | 3.7 | 5/5，期限正確 | 精簡準確、每項都有 refs；**選定** |

速度數字受當時沙盒負載影響，只能相對參考。記憶體：llama-server 匿名記憶體約 3.1～3.7 GB（CPU 版會把權重重新排列成較快的格式，
另佔一份）＋模型檔的記憶體映射（可回收）；ctx 4096 或 KV q8_0 約省 0.5 GB。
**使用者電腦（10 執行緒）預期快 3～4 倍，請以 Windows 實測為準。**

### 沙盒驗證
- 後端 pytest（不含真實模型）全數通過；新增 test_llm_engine（切段、refs→時間、階層整合保留待辦、假 llama-server 的啟動／
  記憶體不足訊息／取消／後端當機時子程序一併結束）、test_summary_api（依序載入、取消、MODEL_LOCK、缺模型時的下載說明）。
- test_llm_real（真實 Qwen3.5-4B）：會議的 5 個負責人全部正確、時間有效、關鍵字含「中山店」；
  分段＋整合模式下全文摘要保留 LINE 與 9/20、問題含 POS、5 個負責人全部保留；任務結束後 llama-server 程序確實結束。
- 前端 vitest、typecheck、build 通過；SummaryCard 以真實輸出截圖檢查（分頁、時間標籤捲動、處理中狀態）。

### Windows 驗收（2026-11-10，使用者本機 931d9c5＋519e8d7）
- llama.cpp 固定為 **b11312**（正好是 commit 0c1e570 的 release），win-cpu-x64 zip 19,265,352 bytes、SHA-256 d2d966c2…；
  download_models --llm／--verify 正常（模型下載約 0.5 MB/s，花了 81 分鐘，HF 未登入）。
- pytest 118 passed / 4 skipped；Job Object 測試在 Windows 通過；test_llm_real：直接模式 223 秒、分段整合模式 1,370 秒（約 23 分鐘）。
- 實測：中文錄音勾選 7 種摘要共 32 分 43 秒；完成與取消後沒有殘留 llama-server.exe；摘要沒有錄音中不存在的人名、數字、日期；
  時間標籤捲動、摘要完成通知、摘要中擋下重新抽取／重新辨識都正常。
- 工作管理員預設的「記憶體」欄位（私人工作集）只看到約 52 MB：llama.cpp 以 mmap 載入模型，不算在這個欄位，要看「尖峰工作集」。
- 修正（Claude Code 發現）：摘要或辨識中從首頁更換檔案時，前端沒有重設逐字稿／摘要狀態，卡片停在「進行中」、防睡眠不解除。
  importFile 開始上傳時一併清除，並補測試。
- macOS 的 llama.cpp 是 .tar.gz：runtime 改為能安全解壓 .zip 與 .tar.gz（拒絕路徑穿越與跳出資料夾的連結），resolver 也找 .tar.gz；
  macOS 項目在 Phase 11 填入。
- 語音辨識結果新增 timings（辨識、對齊各花多少秒，含載入模型），工作區顯示，用來評估使用者提議的「辨識與對齊同時進行」。

### 程式圖示（2026-11-10，使用者選 A：圓角方形黑底、白色兔頭雙耳直立、粗體 M）
- `apps/desktop/scripts/generate_icons.py`（**只用標準函式庫**：自行光柵化＋寫 PNG／ICO，不需要 Pillow）產生
  `build/icon.ico`（16/32/48/256）、`build/icon.png`（512）、`public/favicon.ico`（16/32/48）。
  48 以上由向量形狀 4×4 超取樣；**16、32 是手工像素圖**（耳朵簡化成 2／4 像素寬、M 筆畫 2～3 像素），避免縮小後糊掉。
- BrowserWindow 設定 icon（Windows 用 .ico，其他用 .png）；index.html 加 favicon。安裝程式圖示在 Phase 11 使用同一個 .ico。
- 開發模式（npm run dev）的工作列可能仍顯示 Electron 的圖示（AppUserModelID 是 electron.exe），正式打包後才會完全一致。
- 語音辨識加速：使用者同意「先量測再決定」，等 Windows 上的辨識／對齊時間回報後再在沙盒比較方案。

## 防睡眠修正與開發模式重新載入（2026-11-09）

Windows 驗收（Claude Code 回報，筆電為 Modern Standby，不支援 S3）：通知 ✅、首頁／引導 ✅、螢幕自動關閉與 2 分鐘睡眠後辨識都能繼續 ✅。
兩個發現：
1. **`powerSaveBlocker('prevent-app-suspension')` 在 Windows 8 以後是 PowerRequestExecutionRequired**：
   `powercfg /requests` 中 electron.exe 只出現在「執行」，SYSTEM 是空的 → 它不會阻止閒置睡眠
   （先前「睡眠後仍繼續」其實是睡著、喚醒後接著跑）。Electron 沒有「只保持系統清醒、螢幕照常關」的選項。
   修正：後端新增 `app/core/keepawake.py`，TaskManager 在每個工作執行期間以參考計數送出
   **PowerRequestSystemRequired**（PowerCreateRequest＋原因文字，`powercfg /requests` 的 SYSTEM 區段會看到 python.exe
   「MVR2T：正在處理影音…」），最後一個工作結束時清除；失敗只記錄 `[power] could not …`，不影響工作。
   Electron 端的 ExecutionRequired 保留（讓程式不被暫停）。macOS／Linux 目前為 no-op。
   **Windows 已確認（使用者 a5638ec，Modern Standby 筆電）**：辨識中 `powercfg /requests` 的 SYSTEM 區段有 python.exe 與原因文字、
   結束後消失；螢幕閒置關閉並超過睡眠時間，沒有出現 `[power] system suspend`，辨識持續進行。
   `MVR2T_DEV_NO_HMR=1` 時闔上筆電再打開，畫面與辨識進度保留、工作接著進行。pytest 100 passed / 4 skipped（Windows）。
2. **開發模式闔上筆電後頁面被清空**：不是後端或畫面行程的問題（醒來後同一個工作仍回 200，沒有 `[renderer] gone`），
   而是 Vite 開發伺服器的客戶端在 websocket 斷線、重新連上後執行 `location.reload()`。正式版（`npm start`）沒有這個行為，實測畫面與辨識都保留。
   在開發模式要測睡眠時，設定 `MVR2T_DEV_NO_HMR=1` 會關閉 HMR 與 websocket（`server.hmr=false`、`server.ws=false`；
   只設 `hmr:false` 仍會重新載入，沙盒實測）。代價：改程式後要手動 Ctrl+R，主控台會出現 websocket 連線失敗訊息，可忽略。

## 優化：完成通知、睡眠與螢幕關閉、首頁精簡、引導簡化（2026-11-09）

使用者回饋四點：
1. **逐字稿完成要跳通知** → Renderer 監看 sessionStore：語音辨識從進行中變成完成／失敗時，經 IPC `app:notify`
   請 Main 顯示系統通知（Electron `Notification`），並 `flashFrame` 閃爍工作列；**只有程式不在前景時才通知**
   （在前景時畫面上已看得到）。點通知把視窗帶回前景。通知內容在 Main 以 `parseNotification` 驗證（只收兩個字串、去控制字元、限長）。
   Windows 需要 AppUserModelID：正式版 `com.mvr2t.desktop`，開發時用 `process.execPath`（沒有開始功能表捷徑時自訂 ID 不會顯示通知）。
   Windows「專注輔助／請勿打擾」開啟時通知不會跳出。
2. **螢幕關閉後辨識內容消失** → 調查結論（沙盒無法重現，屬推論）：
   - 輪詢工作進度時**只要一次連線失敗就把工作標成失敗**，進度區塊被錯誤訊息取代；但後端工作其實還在跑。
     電腦睡眠／Modern Standby（螢幕關閉後系統進入待命並暫停桌面程式）醒來那一刻很容易遇到。
   - 修正：連線失敗（ApiError status 0）時保留目前進度、顯示「連線中斷，重新連線中…」，每 2 秒重試，連續 150 次才放棄
     （以次數計，睡眠期間不算）；後端回應的真正錯誤（4xx/5xx）仍立即顯示。
   - 處理中（匯入、抽取、辨識）經 IPC `power:keep-awake` 啟用 `powerSaveBlocker('prevent-app-suspension')`，結束後解除；
     螢幕仍可關閉。闔上筆電或手動睡眠無法阻止，處理會暫停、喚醒後繼續。處理中畫面加上一行說明。
   - Main 記錄 `[power] system suspend / resume`、`[power] keep awake: on/off`、`[renderer] gone: …`，再發生時可從終端機判斷原因。
   - **待使用者在 Windows 確認**：辨識中讓螢幕自動關閉（不闔蓋）幾分鐘，回來後應該仍在進行或已完成。
     若仍被暫停，備案是處理中改用 `prevent-display-sleep`（螢幕保持亮著），可做成設定選項。
   - 若終端機出現 `[renderer] gone`，代表畫面行程當掉後重新載入，記憶體中的工作階段會遺失（規格 §8.3 不保存），需另行處理。
3. **首頁精簡** → 「AI 模型」「這台電腦」兩張卡片移到模型管理頁（檔案移到 `features/models/`）。
   首頁改為 `SystemNotice`：只有後端沒啟動、缺 FFmpeg、缺語音辨識模型時才顯示提醒與「前往模型管理」。
4. **引導簡化** → 移除「知道了／不再提示」，開啟時每一步都顯示；只能在設定頁關閉。
   注意：先前按過「不再提示」的使用者，設定會保留為關閉，需要到設定頁重新開啟。

## 介面更新：吉祥物 Mono、首頁標題、操作引導（2026-11-09）

使用者要求（Phase 05 之後、Phase 06 之前）：兩張卡片等高、操作引導、像素吉祥物、首頁標題更有視覺感。
設計以 HTML 預覽來回確認 5 版後定稿（outputs/Mono_design_preview_v1～v5.html）。

### 使用者決定
- **Mono**：白色、圓潤的「麻糬」兔子，頭和身體是一整坨；長耳朵、內耳淺灰；**沒有嘴巴，用鼻子表情**（抽動、聞聞）；
  平常看不到手腳，有動作時才出現（揮手、歡呼、捧螢幕、遮眼、跳）；動作要有 Q 彈的擠壓伸展。
  垂耳要看得出是長耳朵（不要像貓耳）。聽音樂、完成時鼻子**不要**變愛心。提示動作＝身體左右晃＋鼻子抽動。
  使用者提供的參考圖之一很像現有角色；只借用通用元素（麻糬感、豆豆眼），Mono 的長耳、灰內耳、鼻子表情維持原創。
- **首頁標題**：A 字彙輪播（Your Media → Video → Record）＋ B 像素音波，**不放吉祥物**；補充說明只留
  「把影片與錄音轉成逐字稿、摘要和心智圖」（原本的「讓影音更方便的被解析」拿掉）。
- **引導**：選「操作後引導」（不是頂部流程列）：下一個按鈕發光＋箭頭，Mono 對話框說明；「知道了」關這一則，
  「不再提示」關全部，可在設定頁重新開啟。

### 實作
- `apps/desktop/scripts/generate_mono_sprite.py`（只用標準函式庫）→ 產生 `src/components/mono/sprite.ts`。
  以橢圓、貝茲曲線「管子」（垂耳）畫形狀，每個部件自動加 1 像素黑框。32×36 像素、5 個灰階色。
  **要改造型請改腳本再重新產生，不要手改 sprite.ts。** 形狀中心一律放在 x=16.0（像素 15 與 16 之間），臉部才會左右對稱
  （第一次放在 15.5，對稱測試抓到半像素偏移）。
- `compose.ts`：部件分層（陰影、尾巴、後耳、身體、腳、前耳、臉、手持道具、手、穿戴道具）→ SVG 橫向色塊。
- `animations.ts`：idle、loading、music（抽取音訊中）、video（匯入檢查／辨識中）、hint（引導）、done、error；
  整體動作（breathe / bounce / sway / jelly）是 index.css 的 CSS keyframes，以底部為支點縮放。
  `prefers-reduced-motion` 時停在第一格、不加動作。
- `features/guide/`：`nextGuideStep()` 純函式決定提示哪一步（open-workspace → extract → transcribe → done；
  處理中、失敗、取消時不提示）；`guideStore` 只把「開關」存在 localStorage（介面偏好，不含媒體資料，符合 §8.3），
  「知道了」只在記憶體、換檔案時清空。`GuideTarget` 包住下一步的按鈕，`GuideCoach` 是 Mono 對話框。
- 首頁 `HeroTitle`：h1 的 aria-label 固定為完整標題，輪播文字 aria-hidden；reduced motion 時改顯示三行標題。
- 設計規範頁（開發模式）新增「吉祥物 Mono」區塊，可看所有動畫與對話框。

### 同步 Claude Code 的本機修正（2026-11-09）
- `9b3a5a8` Windows 記憶體讀數加回 ctypes 型別與錯誤檢查；`5b5b215` stdin 監看改用 PeekNamedPipe（不阻塞管線，
  修正辨識卡在「準備中 0%」）＋回歸測試 `test_spawn_worker_starts_while_stdin_watchdog_runs`。沙盒以 git am 套用。
- 依其原則整理：新增 `app/core/procmem.py`（測試與 benchmark 共用；Windows 用自己的 WinDLL＋argtypes/restype，
  失敗就 raise，**絕不回報假的 0 MB**），`scripts/benchmark_asr.py` 改用它（原本在 Windows 峰值記憶體永遠是 0）；
  `tests/test_lifecycle.py` 的 `pid_alive` 在 Windows 也改為具型別呼叫（OpenProcess 失敗時：87=不存在、5=存在、其他 raise）。
  **規則：ctypes 一律用私有 WinDLL 並宣告 argtypes/restype、檢查回傳值；不要用 `ctypes.windll` 全域實例。**
- `_stdin_is_windows_pipe` 的 GetFileType 已由 Claude Code 在本機改為具型別呼叫（使用者本機 3909935）。
  **沙盒副本尚未同步這個 commit**（patch 未附上）；在同步前，交付時不要包含 `apps/backend/app/main.py`，以免蓋掉它。
- 產生器改為 `write_text(..., newline="\n")`：Windows 上預設寫出 CRLF，內容相同但位元組不同（Claude Code 回報）。

### Windows 驗收結果（2026-11-09）
Claude Code 套用為 e3c87ca：typecheck、vitest 125、pytest 95 passed / 4 skipped、test_procmem 實際執行通過；
README「介面更新驗收清單」全部通過（含 125%／150% 縮放下 Mono 清晰、引導依序出現、「不再提示」重開後保留）。

### ASR 精度基準（使用者電腦，2026-11-09，benchmark_asr，60 秒中文歌曲，10 執行緒）
| 精度 | 載入 | 辨識 | RTF | 峰值記憶體 |
|---|---|---|---|---|
| float32 | 13.7 s | 101.0 s | 1.68 | 4227 MB |
| bfloat16 | 27.7 s | 147.4 s | 2.46 | 2672 MB |

決定：**預設維持 float32**。這顆 CPU 沒有原生 BF16，bfloat16 反而慢 1.5 倍，只省 1.5 GB 記憶體。
Phase 10 硬體偵測：只有在可用記憶體不足（float32 約需 4.3 GB）時才退回 bfloat16。
RTF > 1（歌曲有伴奏，比一般說話難；24 分鐘說話錄音實測 RTF 約 1.33）。之後可評估的加速：限制每段最大生成長度、
批次辨識多段、或 Phase 10 有 GPU 時用 CUDA。benchmark 的預覽文字是模型原始輸出（簡體），App 內會經 OpenCC 轉繁體。

- 偶發失敗的 webm 測試：測試影片用無限長的 lavfi 來源＋`-shortest`，長度不固定；改為依 wav 長度明確指定 `d=`。
- 逐字稿載入模型時顯示不確定進度與提示；「部分估計」時說明有幾句是估計時間。

## Phase 05 ASR Integration — 實作與驗證（2026-11-09）

### 環境
- 使用者開放 huggingface.co、*.hf.co、download.pytorch.org。download.pytorch.org 會轉址到 download-r2.pytorch.org（未開放），
  所以沙盒改從 PyPI 安裝 torch（Linux 版含 CUDA 函式庫，約 5 GB，CPU 照常執行）。Windows / macOS 的 PyPI torch 本來就是 CPU 版。
- 固定版本：torch 2.14.1、transformers 5.20.2、tokenizers 0.23.3、safetensors 0.8.0、numpy 2.4.6（2.5 起不支援 Python 3.11）、
  huggingface_hub 2.2.0（只給下載腳本用）、OpenCC 1.4.2。`uv pip compile --python-platform windows` 確認 Windows 解析成功且不含 CUDA。
- 模型：Qwen/Qwen3-ASR-0.6B-hf @ 7f1569a（1.58 GB）、Qwen/Qwen3-ForcedAligner-0.6B-hf @ c07281d（1.85 GB），Apache-2.0。

### 架構
- `app/models/registry.py`：模型 ID、revision、每個檔案的大小與雜湊（大檔 SHA-256、小檔 Git blob SHA-1）。**模型資訊唯一來源**；
  前端改用 `GET /api/models`，刪除 `shared/constants/models.ts`。
- `app/models/store.py` + `scripts/download_models.py`：逐檔下載到 `.<id>.partial`，全部驗證通過才改名並寫入 `.mvr2t-model.json`
  （已安裝標記）。可續傳、`--verify` 重算雜湊、`--list`。
- 預設資料夾改為與 Electron userData 相同（Windows `%APPDATA%\MVR2T`），手動啟動的後端與下載腳本共用模型；
  test_lifecycle 一律用暫存資料夾，不碰真實 userData。
- `engines/asr/qwen3.py`：Transformers 原生類別，只讀本機（local_files_only + HF_HUB_OFFLINE），torch 延後 import
  （後端啟動 0.39 s、未載入 torch）；StoppingCriteria 讓生成途中可取消；dtype 可設定（預設 float32）。
- `engines/asr/text.py`：依標點切句（處理 Mr. / e.g. 等縮寫）、以字詞時間決定句子起訖、加段落 offset、
  **逐字詞**去除硬切重疊、整句 OpenCC s2twp 轉繁體。
- `engines/asr/pipeline.py`：recognize（ASR 逐段）與 align（對齊逐段）兩步驟；`engines/asr/worker.py`：**每個步驟在新的 spawn 子程序執行**，
  程序結束即釋放全部記憶體；子程序監看父程序，後端消失時自行結束。`services/transcribe.py`：工作、進度、取消、組逐字稿。
- API：`GET /api/models`、`POST /api/asr/transcribe {session_id, media_id, language}`、`GET /api/transcript`。
  一次只允許一個辨識工作；辨識中禁止重新抽取音訊；重新抽取會清除舊逐字稿。
- 前端：AI 模型卡片顯示真實安裝狀態與下載指令；工作區「逐字稿」卡片（語言選擇、進度、取消、警告、逐句時間戳記、精確／估計標記）。

### 實驗發現（決定設計的事實）
1. **模型永遠輸出簡體**，提示詞無法改變（試過「請使用繁體中文」等）；熱詞提示修好一詞卻弄壞另一詞 → 不用提示，改 OpenCC。
   OpenCC 片語轉換會改變字數（U盘→隨身碟），所以只在「句」層級轉換；對齊一律用模型原始簡體文字。
2. **強制指定語言時，模型不輸出語言標記** → 以指定語言為準。
3. **同一程序內卸載模型，記憶體不會還給作業系統**（ASR 卸載後仍約 3.2 GB，每辨識一次再增加）→ 改為子程序。
4. **ASR 與對齊放在同一個子程序仍會累積**：沙盒（約 6 GB 上限）在載入對齊模型時被 OOM 終止（代碼 -9）→ 兩步驟各自一個子程序，
   峰值 = 兩者較大值而非相加。
5. float32 載入峰值約 5.2 GB（bf16 權重轉 fp32 暫存兩份）；bfloat16 約 2.5～3.2 GB，輸出相同。
6. 日文、韓文對齊需要 nagisa / soynlp 斷詞套件，第一版未安裝 → 退回估計時間（有警告）。

### 沙盒驗證（2 核 CPU、float32）
- 中文（Piper TTS 合成 18 秒、4 句）：繁體、4 句、逐字時間、精確時間。
- 英文（LibriSpeech 6 段串接 71.5 秒、跨 3 個 ASR 段）：**WER 3.0%**；6 段的第一個字都在該段於合併檔中的起點被找到
  （+0.5 秒為 LibriSpeech 開頭靜音）→ 時間戳記正確對回原始音訊。
- 長音訊（LibriSpeech 73 段、8 分鐘、16 段）：75 句、時間單調遞增、最後一句結束於 480.88 / 481.0 秒、**WER 4.2%**，耗時 429 秒（RTF ≈ 0.9，含其他測試搶 CPU）。
- 取消：真實模型生成中取消 0.86 秒；Electron UI 1.4 秒；子程序全部結束。
- 記憶體：後端程序在連續兩次辨識後維持 512 → 511 MB（模型不在後端程序中）。
- benchmark（60 秒英文）：float32 RTF 0.68、峰值 5.2 GB；bfloat16 RTF 0.50、峰值 2.5 GB（沙盒 CPU 有原生 BF16/AMX，**Windows 需實測**）。
- 測試：後端 96 passed（含真實模型 4 項；無測試語音時 92 passed + 4 skipped）、前端 118、typecheck、Electron E2E P03 22 / P04 22 / P05 17。

### Windows 套用回饋：漏交原始碼（2026-11-09）
- Claude Code 發現 `app/models/registry.py`、`store.py`（以及原本就有的 `app/models/__init__.py`）不在交付內容中，後端無法啟動。
  原因：`.gitignore` 的 `models/` 沒有限定路徑，連 `apps/backend/app/models/`（原始碼）都被排除；交付清單由 `git diff` 產生，
  所以被忽略的新檔案悄悄漏掉。沙盒測試在「工作目錄」執行，檔案都在，因此沒抓到。
- 修正：`/models/`、`/runtime/`、`/temp/` 限定在專案根目錄（權重副檔名規則保留）；補進 3 個檔案；
  `git ls-files --others --ignored --exclude-standard` 確認除了相依套件與建置輸出外，沒有任何被忽略的檔案。
- **新規則：每次交付前，從 `git clone` 出的乾淨資料夾重跑全部測試**（npm ci、typecheck、vitest、build、pytest），
  確保交付內容本身就是完整的。本次已用乾淨複本驗證：pytest 92 passed + 4 skipped、vitest 118、typecheck、build 皆通過。
- Claude Code 的執行環境安裝 torch 時出現 `SSL CERTIFICATE_VERIFY_FAILED`（連 pypi.org），使用者改在自己的終端機安裝。

### Windows 套用回饋：只在 Linux 跑過的程式（2026-11-09）
- Claude Code 在 Windows 發現 `tests/test_asr_real.py` 頂層 `import resource`（Unix 專用）→ pytest 收集階段中斷，整個後端測試沒執行。
  本機修正 38cb148；Cowork 已同步（改寫為相同效果）。
- Cowork 依建議全面掃描平台限定寫法，另外找到：
  1. `test_asr_real.py` 用 `symlink_to()` 指向真實模型 → Windows 需開發人員模式或系統管理員權限。改為新增設定
     `MVR2T_MODELS_DIR`（也讓使用者能把模型放在其他磁碟），測試直接指向真實模型資料夾。
  2. `test_transcribe_service.py` 用 `truncate()` 建立 1.5 GB 假模型檔 → Linux 為稀疏檔不佔空間，
     **Windows/NTFS 會真的配置磁碟空間**，且 pytest 保留最近 3 次的暫存資料夾，可能佔用數十 GB。改為 monkeypatch「已安裝」判斷。
  3. 記憶體測試原本用 `import torch` 檢查是否安裝，使「後端程序不得載入 torch」無法斷言 → 改用 `importlib.util.find_spec`。
     現在斷言後端程序完全沒有載入 torch，後端 RSS 111 → 110 MB。
- 其他命中（`benchmark_asr.py` 的 resource、`test_lifecycle.py` 的 /proc）已在平台判斷之內，無需修改。
- **交付前跨平台檢查清單**（Python）：`resource`、`fcntl`、`termios`、`pwd`、`grp`、`os.getuid`、`os.fork`、`/proc`、
  `symlink`、`os.kill(pid, 0)`（Windows 會終止行程）、`SIGKILL`、`shell=True`、`truncate()` 建大檔、寫死的 `/tmp`。
  可用：`grep -rnE "import (resource|fcntl|termios|pwd|grp)|os\.getuid|os\.fork|/proc/|symlink|truncate\(|/tmp" --include=*.py apps/backend`

### 已知限制 / 待辦
- 預設 float32；待使用者的 benchmark 結果決定是否改為 bfloat16（Phase 10 硬體偵測自動選擇）。
- 辨識途中不即時顯示部分文字（完成後一次顯示）。
- 逐字稿編輯、依時間戳記播放原始影音、匯出 SRT 等：後續 Phase。
- 打包（Phase 11）注意：worker 使用 multiprocessing spawn，PyInstaller 需 `multiprocessing.freeze_support()`。

## Phase 05 ASR Integration — 調查與決策（2026-11-09）

### 調查結果（官方 README：github.com/QwenLM/Qwen3-ASR）
- Qwen3-ASR（0.6B / 1.7B，Apache-2.0）**只輸出文字與語言，不輸出時間戳記**。時間戳記需另一個模型
  Qwen3-ForcedAligner-0.6B（Apache-2.0，單檔 model.safetensors 1.84 GB，NAR 單次前向，**每次最多 5 分鐘**，
  支援 11 種語言：中、英、粵、法、德、義、日、韓、葡、俄、西）。規格 §5.2「先用 ASR 本身的時間資訊」不成立。
- 2026-06-26 起 Transformers 原生支援（`-hf` 模型）：transformers 5.x 內建 `models/qwen3_asr`
  （`Qwen3ASRForConditionalGeneration`、對齊用 `Qwen3ASRForTokenClassification`，processor 有
  `apply_transcription_request`、`decode(return_format="parsed")`、`prepare_forced_aligner_inputs`、`decode_forced_alignment`）。
  transformers 5.x 需 Python ≥ 3.11、torch ≥ 2.6。
- 官方 `qwen-asr` 套件（0.0.6）固定 transformers==4.57.6，並拉進 gradio、flask、librosa、sox 等，不利 PyInstaller 打包 → **不採用**，
  改用 Transformers 原生路線（也符合規格「優先測試官方 Transformers Backend」）。
- 沙盒連不到 huggingface.co、modelscope.cn、download.pytorch.org（代理拒絕）；PyPI、GitHub raw 可連。

### 使用者決策
1. 使用者會在 claude.ai 開放網域（huggingface.co、hf.co、download.pytorch.org），讓沙盒以 CPU 實際辨識驗證。
2. **加入 ForcedAligner**：ASR 完成 → 卸載 → 載入對齊模型（依序載入）。不支援的語言退回切段層級時間。
3. 使用者電腦**沒有／不確定 NVIDIA GPU → 開發環境裝 CPU 版 PyTorch**（GPU 路線留到 Phase 10）。
4. 開發期以**下載腳本**取得模型，放在 `%APPDATA%\MVR2T\models\`（與 Phase 09 相同位置），模型 ID 與 revision 集中在一處。

## Phase 04 Media Processing（2026-11-07）

### 使用者決定
- FFmpeg：**程式自動尋找**（設定資料夾 → `<userData>/runtime/ffmpeg` → PATH → winget 安裝位置），開發時以 `winget install Gyan.FFmpeg` 安裝。
  未選 imageio-ffmpeg：它只附 ffmpeg、沒有 ffprobe，且正式版大概率要換。正式安裝檔附哪個 FFmpeg（LGPL 組態）留到 Phase 11。
- 匯入：**先複製一份到 Session 暫存**（規格 §8.3「原始媒體副本」），不直接讀原始檔。

### 架構
- 後端
  - `engines/media/ffmpeg.py`：尋找 FFmpeg、ffprobe 解析、抽取指令（`-nostdin`、`-map 0:a:0`、16 kHz 單聲道 PCM、`silencedetect`、`-progress pipe:1`）。
    子行程一律 `stdin=DEVNULL`（後端 stdin 是 Electron 的生命週期管線）、參數陣列、Windows `CREATE_NO_WINDOW`。
  - `engines/media/segmenter.py`：目標 30 秒、±8 秒視窗內找**最長停頓的中點**下刀；找不到才硬切並重疊 1 秒；最短 5 秒。
    以 PCM 取樣點從同一個 WAV 擷取，`start` / `end` 為原始時間軸秒數。參數集中在 `SegmentParams`，Phase 05 依實測調整。
  - `services/tasks.py`：背景執行緒工作 + 取消（取消時 kill FFmpeg）。進度以輪詢 `GET /api/tasks/{id}?session_id=` 取得
    （EventSource 不能帶 Authorization 標頭，所以第一版不用 SSE）。
  - `session/manager.py`：`<userData>/temp/sessions/<id>/`。建立新 Session 會結束舊的（單一視窗；重新整理 = 清空）；
    啟動時清除殘留、關閉時清除本次；刪除前檢查路徑必須在 sessions 根目錄內。
  - `services/media.py`：上傳以 `application/octet-stream` 串流寫入（不用 multipart，避免多寫一次），
    後端重新驗證副檔名、大小（10 GB，`MVR2T_MAX_UPLOAD_BYTES`）、磁碟空間；檔名只用於顯示，存成 `original.<ext>`。
    抽取完成寫 `audio/manifest.json`（各段檔案與 start），給 Phase 05 使用。
  - API：`POST /api/session`、`DELETE /api/session/{id}`、`POST /api/media/upload?session_id&filename`、
    `POST /api/media/extract-audio`、`GET /api/tasks/{id}`、`POST /api/tasks/{id}/cancel`、`GET /api/system/ffmpeg`。
  - 路由一律透過 `request.app.state.settings` 讀設定（曾誤用全域 settings，測試傳入的設定被忽略；已修正）。
- 前端：`features/media/mediaController.ts`（流程）、`stores/sessionStore.ts`（只在記憶體）、XHR 上傳（有上傳進度與取消）、
  工作區的影音資訊 / 抽取進度 / 切段表、「這台電腦」卡片的 FFmpeg 狀態與安裝說明。後端一上線就建立 Session（清掉上一次的暫存）；
  偵測到後端換了行程（網址或憑證改變）時清空畫面上的媒體並重建 Session。
- Electron：傳 `MVR2T_DATA_DIR = app.getPath('userData')`；`productName: "MVR2T"` → Windows 為 `%APPDATA%\MVR2T`。

### 沙盒驗證（2026-11-07）
- pytest 67（含真實 FFmpeg 整合測試 31 項）、vitest 111、typecheck、build、`npm audit` 0、`pip-audit` 0。
- 驗收「指定格式」：MP4 / MOV / MKV / WEBM / MP3 / WAV / M4A / FLAC / AAC / OGG 全部可匯入、抽取。
- 驗收「時間偏移」：在原始音訊的已知時間放入短促標記，經過上傳 → 抽取 → 切段後，從各段檔案找回標記：
  `段.start + 段內位置 = 原始時間`。無損格式誤差 ≤ 3 ms，有損格式 ≤ 30 ms；硬切重疊區內的標記在兩段中都對回同一時間。
- 30 分鐘音訊：抽取 + 切段 1.4 秒、49 段。4 小時音訊可在中途取消。
- 損壞檔、沒有音訊軌的影片、超過大小上限、`../../` 檔名、FFmpeg 不存在：皆有清楚的繁中訊息且不留暫存。
- 真實 Electron E2E 22/22（正式版）：啟動清除殘留、FFmpeg 狀態、中文檔名匯入、抽取與切段表、取消、換檔、重新整理清空、
  關閉清空、找不到 FFmpeg 的說明；無 CSP 違規。Phase 03 E2E 22/22、Phase 02 截圖 26/26 未退步。

### Windows 套用回饋（2026-11-08）
- 本機以 commit 886abe1 原封不動套用（42 個檔案；Cowork 先前說「43」是把清單標題行算進去了）。npm test 111、typecheck 通過。
- **pytest 在 Windows 2 項失敗**：`test_locate_*` 只 mock 了 `shutil.which`，沒 mock `_winget_candidates()`，
  而使用者電腦真的有 winget 安裝的 Gyan.FFmpeg。Claude Code 已在本機修正（6299ecb）；Cowork 已同步，
  並新增 `test_locate_falls_back_to_winget_install`。**規則：預期「找不到 FFmpeg」的測試都要同時 mock `_winget_candidates`。**
- 使用者電腦有兩份 FFmpeg：PATH 上的 7.1.1 essentials（Downloads 資料夾）與 winget 的 9.0.2 full_build；依尋找順序使用 PATH 的 7.1.1。
- 使用者回報「取消後停住、無法重新上傳」。**實際情境是首頁匯入（正在複製到工作階段）途中按取消**，不是抽取音訊。
  Cowork 誤判為抽取取消，fix1 加的卡片內「換一個檔案」按鈕處理的是另一個情境（仍保留，屬 UX 改善）。
  根本原因（Claude Code 在本機 43036b9 找到並修正）：`cancelImport()` 先把 `uploadController` 設為 null 再 abort，
  `importFile` 的 catch 因此把「使用者取消」誤判成「被新的上傳取代」而直接 return，畫面停在 uploading。
  修正：`cancelImport()` 在 abort 後呼叫 `resetMedia()`。Cowork 已同步，並以真實 Electron（限速上傳 4 MB/s、15% 時取消）
  確認：舊程式碼卡住、新程式碼回到拖放區、部分上傳的檔案被刪除、可重新匯入。
  **教訓：原本的單元測試讓 uploadMedia 直接丟 AbortedError，沒經過 cancelImport()；沙盒 E2E 只測了抽取取消，沒測上傳取消
  （本機上傳太快來不及按）。之後的取消類測試要走「使用者實際按的那個函式」，E2E 需要限速才能測上傳中的操作。**

### 已知限制 / 教訓
- AAC 等有損格式的停頓邊界會偏移幾毫秒、結尾多約 19 ms padding，屬正常；測試以「切點落在停頓內」驗證。
- **Playwright 在 Electron 中無法用 setInputFiles 傳入路徑含中文的檔案**（不觸發 change 事件）。這是測試工具限制，
  App 本身已用拖放路徑驗證中文檔名可正常匯入；E2E 以「在頁面中建立同名 File 並拖放」測試。
- Windows 上被終止的 FFmpeg 若因防毒軟體延遲釋放檔案，刪除暫存可能失敗；下次啟動會再清除。
- 播放器、依時間戳記定位原始影音尚未實作（需要能帶憑證的媒體串流，與逐字稿一起在後續 Phase 處理）。

## Phase 03 驗收備註（2026-11-07）

- 關閉視窗：stopping → stdin closed → stopped，`npm run dev` 結束代碼 0、無 npm error（使用者在後端仍在啟動中時關閉，也正常）。
- Electron 被強制結束 → 後端自行結束：已由 Windows 上的 Ctrl+C 情境證實（cli.js 在 Windows 會 TerminateProcess Electron）。
- **延後**：「在工作管理員手動結束 .venv 啟動器 python.exe」是否會留下實際伺服器。屬人為操作的少見情境；
  Windows venv 啟動器以 Job Object 管理子行程，預期會一併結束。Phase 11 改用 PyInstaller 單一執行檔後此情境消失。

## 依賴升級（2026-11-07，使用者同意在 Phase 04 前進行）

| 套件 | 舊 | 新 | 備註 |
|---|---|---|---|
| electron | 33.2.1（已停止支援） | 44.10.2 | 44 系列已發布 2.5 個月；未選剛發布兩週的 45。extract-zip 弱點一併消失 |
| esbuild | 0.24.0 | 0.28.2 | |
| vite | 5.4.11 | 6.4.5 | 5.x 已無修補版；6.4.4 起修正所有回報弱點 |
| vitest | 2.1.5 | 4.1.12 | 2.x / 3.x 無法修正 tinypool、@vitest/mocker 弱點 |
| postcss | 8.4.47 | 8.5.32 | |
| fastapi | 0.115.5 | 0.162.0 | |
| starlette | （未固定，0.41.3） | 1.7.0 | 改為明確固定；0.41.x 有多項弱點 |
| uvicorn | 0.32.1 | 0.54.0 | |
| pydantic / anyio | （未固定） | 2.13.5 / 4.15.1 | 改為明確固定，消除 anyio 棄用警告來源 |
| pytest | 8.3.3 | 9.1.1 | |
| httpx | 0.27.2 | httpx2 2.13.1 | starlette 1.x 的 TestClient 建議改用 httpx2（同作者，pydantic 組織維護） |

結果：`npm audit` 0、`pip-audit` 0；pytest 16（無警告）、vitest 81、typecheck、build、UI 截圖 26/26、
Electron E2E 22/22（正式版 + 開發版）、SIGINT 優雅結束皆通過，畫面與升級前一致。

升級中發現：
- **npm 10 的 `edgesOut` 錯誤**：沒有 lockfile 或新增套件時，npm 10 在處理 vitest 4 的選用 peer 依賴時崩潰。
  已用 npm 11 產生 `package-lock.json`；有 lockfile 時 npm 10 的 `npm ci` / `npm install` 正常。
  **之後新增 npm 套件請用 `npx npm@11 install -E -w @mvr2t/desktop <套件>@<版本>`**，並把 lockfile 一起提交。
- npm 11.21 預設會擋套件的 install script（esbuild 的 postinstall 只是最佳化，不影響使用）。
- Electron 44 不再有 postinstall：**第一次執行時才下載 Electron 執行檔**（約 100 MB，終端機顯示 `Downloading Electron binary...`）。
- Vite 6 會把 CSP meta 的單引號寫成 `&#39;`，屬合法 HTML，實測 CSP 正常生效。
- Windows 驗收時 `tests/test_lifecycle.py` 4 項失敗：測試假設「spawn 的 PID = 伺服器回報的 PID」，
  但以 `.venv\Scripts\python.exe -m pytest` 執行時 `sys.executable` 是 venv 啟動器。已改為：Windows 不比對 PID，
  改記錄伺服器 PID 並在結束後確認它真的消失（不使用 os.kill(pid, 0)，在 Windows 會終止行程），清理改用 taskkill /T。
  **規則：任何牽涉 PID 的程式或測試，都要考慮 Windows venv 啟動器的兩層行程。**
- Playwright 的 `electronApp.process()` 在 Electron 44 無法使用；E2E 改用 `app.evaluate(() => process.pid)` 取得主行程 PID。

## 套用到使用者電腦時（依賴升級版）

1. 解壓縮覆蓋專案（保留 `apps/backend/.venv`）。
2. 後端：`apps\backend\.venv\Scripts\python.exe -m pip install -r apps\backend\requirements\dev.txt`
3. 前端：根目錄 `npm ci`（依 lockfile 安裝，會先自動清掉舊的 node_modules）。
4. 第一次 `npm run dev` 會下載 Electron 44 執行檔。
