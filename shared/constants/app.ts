/**
 * 跨 Electron main / preload / renderer 共用的常數。
 * 注意：此檔案必須是「環境中立」的純 TS（不可使用 DOM 或 Node API），
 * 因為三個環境都會引用它。
 *
 * 規格第 16 條：模型 ID / 版本 / 下載來源集中在後端 apps/backend/app/models/registry.py，前端透過 GET /api/models 取得。
 */

export const APP_NAME = 'MVR2T - Local Media Studio';
export const APP_TAGLINE = 'Your Media. Your Video. Your Record.';

/**
 * 後端只監聽 127.0.0.1（規格 §3.3）。
 * Phase 03 起由 Electron 啟動後端並使用作業系統分配的連接埠；
 * 以下固定位址只用於「瀏覽器預覽 + 手動啟動後端」的開發情境。
 */
export const DEFAULT_BACKEND_HOST = '127.0.0.1';
export const DEFAULT_BACKEND_PORT = 8765;
export const DEFAULT_BACKEND_URL = `http://${DEFAULT_BACKEND_HOST}:${DEFAULT_BACKEND_PORT}`;

/** 後端啟動後在 stdout 輸出的就緒標記（需與 apps/backend/app/core/config.py 的 READY_MARKER 一致）。 */
export const BACKEND_READY_MARKER = 'MVR2T_BACKEND_READY';

/** Electron IPC 頻道名稱（Renderer ↔ Main）。 */
export const IPC_CHANNELS = {
  getAppInfo: 'app:get-info',
  getBackendState: 'backend:get-state',
  restartBackend: 'backend:restart',
  /** Renderer → Main：顯示系統通知（例如逐字稿完成）。 */
  notify: 'app:notify',
  /** Renderer → Main：處理中時防止電腦自動睡眠。 */
  setKeepAwake: 'power:keep-awake',
  /** Renderer → Main：以「另存新檔」對話框儲存匯出的檔案（心智圖 PNG／SVG；Phase 08 起更多格式）。 */
  saveFile: 'file:save',
  /** Renderer → Main：匯出面板（Phase 08）。選資料夾後，由 Main 向後端取得檔案（PDF 由 Main 列印）並寫入。 */
  exportFiles: 'file:export',
  /** Renderer → Main：在檔案總管中開啟「最近一次匯出」的資料夾（renderer 不能指定路徑）。 */
  openExportFolder: 'file:open-export-folder',
  /** 匯出資料夾偏好（上次的資料夾、設定中的固定資料夾） */
  getExportPrefs: 'prefs:get-export',
  chooseFixedExportFolder: 'prefs:choose-export-folder',
  clearFixedExportFolder: 'prefs:clear-export-folder',
  /** YouTube 下載使用說明：是否已同意（userData/preferences.json） */
  getYouTubeNotice: 'prefs:get-youtube-notice',
  acceptYouTubeNotice: 'prefs:accept-youtube-notice',
  /** Main → Renderer 推送後端狀態變化。 */
  backendStateChanged: 'backend:state-changed',
} as const;

/** 匯出（Phase 08）：內容 → 支援的格式。後端 apps/backend/app/services/export.py 的 FORMATS 需一致（pdf 由後端 html 轉成）。 */
export const EXPORT_FORMATS = {
  segments: ['txt', 'csv', 'docx', 'pdf'],
  segments_audio: ['zip'],
  transcript: ['txt', 'srt', 'vtt', 'json', 'csv', 'docx', 'pdf'],
  summary: ['md', 'txt', 'csv', 'json', 'docx', 'pdf'],
  mindmap: ['png', 'svg'],
} as const;

/** 匯出檔名中的內容名稱：<媒體檔名>-<名稱>.<副檔名> */
export const EXPORT_LABELS = {
  segments: '切段清單',
  segments_audio: '切段音檔',
  transcript: '逐字稿',
  summary: '摘要',
  mindmap: '心智圖',
} as const;
