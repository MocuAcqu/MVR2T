/**
 * Electron Main Process（規格 §3.2）
 * 職責：視窗管理、應用程式生命週期、IPC、Python Backend 生命週期（Phase 03）。
 */
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Notification,
  powerMonitor,
  powerSaveBlocker,
  session,
  shell,
  type IpcMainInvokeEvent,
} from 'electron';
import { APP_NAME, IPC_CHANNELS } from '@shared/constants/app';
import type { AppInfo, BackendState, SaveFileResult } from '@shared/types/ipc';
import { BackendManager, resolveBackendCommand } from './backend';
import { isAppUrl, isSafeExternalUrl, parseNotification, parseSaveRequest, rendererOrigins } from './security';

// 開發模式：由 `npm run dev` 注入 Vite dev server 位址；正式版則載入打包後的 index.html。
const devServerUrl = process.env.VITE_DEV_SERVER_URL;
const indexFile = path.join(__dirname, '../dist/index.html'); // dist-electron/main.js → ../dist/index.html
const indexFileUrl = pathToFileURL(indexFile).href;
const appUrlOptions = { devServerUrl, indexFileUrl };

// 進階 / 除錯用：設定 MVR2T_BACKEND_URL 時改連「手動啟動」的後端，Electron 不會自行啟動。
const externalBackendUrl = process.env.MVR2T_BACKEND_URL;

// ---------------------------------------------------------------------------
// Backend
// ---------------------------------------------------------------------------

function broadcast(state: BackendState): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send(IPC_CHANNELS.backendStateChanged, state);
  }
}

const backend = new BackendManager({
  resolve: () =>
    resolveBackendCommand({
      platform: process.platform,
      isPackaged: app.isPackaged,
      // dist-electron/ → apps/desktop/ → apps/backend/
      backendDir: process.env.MVR2T_BACKEND_DIR ?? path.resolve(__dirname, '../../backend'),
      resourcesPath: process.resourcesPath,
      pythonOverride: process.env.MVR2T_PYTHON,
    }),
  allowedOrigins: rendererOrigins(devServerUrl),
  // 例如 Windows：%APPDATA%\\MVR2T；暫存在其下的 temp\\sessions\\
  dataDir: app.getPath('userData'),
  onState: (state) => {
    console.log(`[backend] ${state.phase}${state.pid ? ` pid=${state.pid}` : ''}${state.url ? ` ${state.url}` : ''}${state.message ? ` - ${state.message}` : ''}`);
    broadcast(state);
  },
  onLog: (line) => console.log(`[backend] ${line}`),
});

function currentBackendState(): BackendState {
  if (externalBackendUrl) {
    return {
      phase: 'running',
      url: externalBackendUrl,
      token: process.env.MVR2T_AUTH_TOKEN ?? null,
      pid: null,
      message: null,
      logTail: [],
      mode: 'external',
    };
  }
  return backend.getState();
}

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

/** 開發模式的 CSP（正式版由 vite.config 寫入 index.html 的 meta）。Vite HMR 需要 inline script 與 websocket。 */
function installDevCsp(): void {
  if (!devServerUrl) return;
  const { host } = new URL(devServerUrl);
  const csp = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "media-src 'self' blob:",
    `connect-src 'self' ws://${host} http://127.0.0.1:*`,
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join('; ');
  session.defaultSession.webRequest.onHeadersReceived({ urls: [`${devServerUrl}/*`] }, (details, callback) => {
    callback({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [csp] } });
  });
}

function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    title: APP_NAME,
    // 程式圖示（apps/desktop/scripts/generate_icons.py 產生）。dist-electron/ → ../build/
    icon: path.join(__dirname, '../build', process.platform === 'win32' ? 'icon.ico' : 'icon.png'),
    backgroundColor: '#ffffff',
    autoHideMenuBar: true, // Windows/Linux：隱藏預設選單列，按 Alt 顯示
    show: false, // 內容準備好再顯示，避免白屏閃爍
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      // 規格 §11：Renderer 不直接取得 Node.js 權限
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  win.once('ready-to-show', () => win.show());
  win.on('focus', () => win.flashFrame(false)); // 停止通知造成的工作列閃爍

  // 阻擋視窗內任意導航 / 開新視窗
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternalUrl(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!isAppUrl(url, appUrlOptions)) event.preventDefault();
  });
  // 不允許頁面嵌入 <webview>
  win.webContents.on('will-attach-webview', (event) => event.preventDefault());

  if (devServerUrl) void win.loadURL(devServerUrl);
  else void win.loadFile(indexFile);
  return win;
}

// ---------------------------------------------------------------------------
// IPC（規格 §11-8：只暴露有限 API，並驗證呼叫來源）
// ---------------------------------------------------------------------------

/** 只接受「本程式頁面的主框架」發出的 IPC；其他來源（iframe、外部頁面）一律拒絕。 */
function assertTrustedSender(event: IpcMainInvokeEvent): void {
  const frame = event.senderFrame;
  if (!frame || frame !== event.sender.mainFrame || !isAppUrl(frame.url, appUrlOptions)) {
    throw new Error('Blocked IPC call from untrusted sender');
  }
}

function handle<T>(channel: string, fn: (arg: unknown) => T | Promise<T>): void {
  ipcMain.handle(channel, (event, arg: unknown) => {
    assertTrustedSender(event);
    return fn(arg);
  });
}

// ---------------------------------------------------------------------------
// 另存新檔（匯出）：路徑一律由使用者在系統對話框中選擇
// ---------------------------------------------------------------------------

async function saveFile(input: unknown): Promise<SaveFileResult> {
  const req = parseSaveRequest(input);
  if (!req) throw new Error('Invalid save request');
  const win = mainWindow();
  const options = {
    title: '另存新檔',
    defaultPath: path.join(app.getPath('documents'), req.fileName),
    filters: [{ name: req.label, extensions: [req.ext] }],
  };
  const { canceled, filePath } = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options);
  if (canceled || !filePath) return { saved: false, path: null };
  const target = path.extname(filePath).toLowerCase() === `.${req.ext}` ? filePath : `${filePath}.${req.ext}`;
  await writeFile(target, req.bytes);
  return { saved: true, path: target };
}

// ---------------------------------------------------------------------------
// 通知與防止睡眠
// ---------------------------------------------------------------------------

function mainWindow(): BrowserWindow | undefined {
  return BrowserWindow.getAllWindows().find((w) => !w.isDestroyed());
}

/** 程式不在前景時才通知（在前景時畫面上已經看得到結果）。點通知會把視窗帶回前景。 */
function showNotification(input: unknown): boolean {
  const n = parseNotification(input);
  const win = mainWindow();
  if (!n || !Notification.isSupported()) return false;
  if (win && win.isVisible() && win.isFocused() && !win.isMinimized()) return false;
  const notification = new Notification({ title: n.title, body: n.body });
  notification.on('click', () => {
    const w = mainWindow();
    if (!w) return;
    if (w.isMinimized()) w.restore();
    w.show();
    w.focus();
  });
  notification.show();
  win?.flashFrame(true); // Windows：工作列圖示閃爍，直到使用者切回程式
  return true;
}

/**
 * 處理中請系統不要暫停或終止本程式（Windows 8 以後：PowerRequestExecutionRequired，`powercfg /requests` 的「執行」區段）。
 * 注意：這**不會**阻止電腦因閒置而睡眠（2026-11-09 使用者實測）；防止閒置睡眠由後端在工作期間送出
 * PowerRequestSystemRequired（apps/backend/app/core/keepawake.py）。兩者都不影響螢幕依設定關閉。
 * 闔上筆電或手動睡眠無法阻止；喚醒後程序會繼續，前端輪詢也會自動重新連線。
 */
let keepAwakeId: number | null = null;
function setKeepAwake(on: unknown): void {
  if (on === true && keepAwakeId === null) {
    keepAwakeId = powerSaveBlocker.start('prevent-app-suspension');
    console.log('[power] keep awake: on');
  } else if (on !== true && keepAwakeId !== null) {
    powerSaveBlocker.stop(keepAwakeId);
    keepAwakeId = null;
    console.log('[power] keep awake: off');
  }
}

function registerIpc(): void {
  handle(IPC_CHANNELS.getAppInfo, (): AppInfo => ({
    name: APP_NAME,
    version: app.getVersion(),
    platform: process.platform,
    arch: process.arch,
    isPackaged: app.isPackaged,
  }));
  handle(IPC_CHANNELS.getBackendState, currentBackendState);
  handle(IPC_CHANNELS.restartBackend, async () => {
    if (externalBackendUrl) return currentBackendState();
    return backend.restart();
  });
  handle(IPC_CHANNELS.notify, showNotification);
  handle(IPC_CHANNELS.setKeepAwake, setKeepAwake);
  handle(IPC_CHANNELS.saveFile, saveFile);
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

// 單一實例：避免同時啟動兩個程式（各自會啟動一個 Backend）。
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  registerIpc();

  // Windows 通知需要 AppUserModelID。開發時沒有開始功能表捷徑，用 Electron 執行檔路徑才會顯示通知。
  if (process.platform === 'win32') app.setAppUserModelId(app.isPackaged ? 'com.mvr2t.desktop' : process.execPath);

  void app.whenReady().then(() => {
    // 除錯用：睡眠／喚醒與畫面行程異常都記在終端機，方便追查「螢幕關閉後內容消失」這類問題。
    powerMonitor.on('suspend', () => console.log('[power] system suspend'));
    powerMonitor.on('resume', () => console.log('[power] system resume'));
    app.on('render-process-gone', (_e, _wc, details) => console.log(`[renderer] gone: ${details.reason} (exit ${details.exitCode})`));
    installDevCsp();
    // 視窗與後端同時啟動；畫面會顯示「後端啟動中」直到健康檢查通過。
    if (!externalBackendUrl) void backend.start();
    createMainWindow();
    // macOS：點擊 Dock 圖示且沒有視窗時重新建立
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
    });
  });

  // Windows / Linux：關閉所有視窗即結束；macOS 依慣例保留程式（後端也保留，Cmd+Q 才結束）
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  // 結束前先讓後端優雅關閉，再真正結束程式（Phase 03 驗收：關閉程式時後端正常結束）。
  let backendStopped = false;
  let stopping = false;
  app.on('before-quit', (event) => {
    if (backendStopped || externalBackendUrl) return;
    event.preventDefault();
    if (stopping) return;
    stopping = true;
    void backend.stop().finally(() => {
      backendStopped = true;
      app.quit();
    });
  });

  // 在終端機按 Ctrl+C（或收到結束訊號）時，也走正常的結束流程，讓後端優雅關閉。
  for (const signal of ['SIGINT', 'SIGTERM'] as const) {
    process.on(signal, () => app.quit());
  }

  // 最後防線：任何原因導致主行程結束時，同步終止後端。
  // （Electron 被強制結束時，作業系統會關閉 stdin 管線，後端也會自行結束。）
  process.on('exit', () => backend.killNow());
}
