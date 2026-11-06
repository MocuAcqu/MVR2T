# 開發紀錄（給接手的 Claude / Claude Code）

最後更新：2026-11-07。Phase 02 / 03 已在 Windows 驗收；依賴升級已在沙盒完成驗證，待 Windows 驗收後開始 Phase 04。

## 目前進度

| Phase | 狀態 |
|---|---|
| 01 專案初始化 | ✅ 使用者已在 Windows 驗收通過（Electron 視窗開啟、後端已連線、Python 3.11.6） |
| 02 UI 設計系統 | ✅ 使用者已在 Windows 驗收通過（2026-11-06） |
| 03 Electron 啟動 Python Backend | ✅ 使用者已在 Windows 驗收通過（2026-11-07；手動結束啟動器一項延後，見下方） |
| 依賴升級 | 🟡 沙盒驗證通過，**待 Windows 驗收** |
| 04 Media Processing | ⬜ 依賴升級驗收後開始 |

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
