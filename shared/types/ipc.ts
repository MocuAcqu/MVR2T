/** Electron Main 回傳給 Renderer 的應用程式資訊。 */
export interface AppInfo {
  name: string;
  version: string;
  platform: string; // process.platform：win32 / darwin / linux
  arch: string; // process.arch：x64 / arm64
  isPackaged: boolean;
}

/**
 * 由 Electron 管理的後端行程狀態（Phase 03）。
 * - starting：行程已啟動，等待健康檢查通過
 * - running：可使用；url 與 token 有值
 * - stopping：程式結束中
 * - stopped：尚未啟動，或已正常結束
 * - error：找不到 Python、啟動逾時或行程意外結束；message 給使用者看，logTail 給除錯用
 */
export type BackendPhase = 'starting' | 'running' | 'stopping' | 'stopped' | 'error';

export interface BackendState {
  phase: BackendPhase;
  /** running 時才有值，例如 http://127.0.0.1:51234 */
  url: string | null;
  /**
   * 一次性連線憑證。只交給本程式的視窗；其他本機網頁沒有它就無法呼叫後端。
   * 每次啟動後端都會重新產生。
   */
  token: string | null;
  /** 後端行程 PID（除錯與驗收用）。 */
  pid: number | null;
  /** 使用者看得懂的錯誤說明（繁體中文）。 */
  message: string | null;
  /** 最後幾行後端輸出，協助排查。 */
  logTail: string[];
  /** 'managed' = Electron 啟動；'external' = 透過 MVR2T_BACKEND_URL 使用手動啟動的後端。 */
  mode: 'managed' | 'external';
}

/** 系統通知內容（逐字稿完成、處理失敗等）。 */
export interface AppNotification {
  title: string;
  body: string;
}

/** 可匯出的檔案種類。png：data 為 base64；其他：data 為 UTF-8 文字。 */
export type SaveFileKind = 'png' | 'svg';

export interface SaveFileRequest {
  /** 建議檔名（不含路徑；副檔名會依 kind 補上） */
  defaultName: string;
  kind: SaveFileKind;
  data: string;
}

export type ExportContent = 'segments' | 'segments_audio' | 'transcript' | 'summary' | 'mindmap';
export type ExportFormat = 'txt' | 'csv' | 'docx' | 'pdf' | 'srt' | 'vtt' | 'json' | 'md' | 'zip' | 'png' | 'svg';

export interface ExportItem {
  content: ExportContent;
  format: ExportFormat;
}

/** 匯出面板 → Main。檔案存到使用者在對話框中選的資料夾。 */
export interface ExportFilesRequest {
  sessionId: string;
  mediaId: string;
  /** 媒體檔名（不含副檔名也可以）；檔名為 <baseName>-<內容>.<格式> */
  baseName: string;
  items: ExportItem[];
  /** 編輯後的心智圖（樹）；摘要匯出時使用 */
  mindmap?: unknown;
  /** 心智圖 PNG（base64）：心智圖 PNG 與摘要 DOCX／PDF 使用 */
  mindmapPng?: string;
  /** 心智圖 SVG（UTF-8 文字） */
  mindmapSvg?: string;
  /** 只匯出這些摘要類型（含 'mindmap'）；不給 = 全部 */
  summaryTypes?: string[];
  /** 已在設定指定固定資料夾時，這次仍跳出對話框選資料夾 */
  askFolder?: boolean;
}

/** 匯出資料夾的偏好（只存路徑，不存任何媒體或逐字稿內容）。存在 Main 的 userData/preferences.json。 */
export interface ExportPrefs {
  /** 上次選的資料夾（下次對話框從這裡開始） */
  lastFolder: string | null;
  /** 設定中指定的固定資料夾：指定後匯出不再詢問 */
  fixedFolder: string | null;
  /** 固定資料夾目前是否存在（例如隨身碟拔掉時為 false，匯出會改為詢問） */
  fixedFolderAvailable: boolean;
}

export interface ExportItemResult extends ExportItem {
  ok: boolean;
  /** 成功時寫入的完整路徑 */
  path: string | null;
  /** 失敗時給使用者看的說明 */
  error: string | null;
}

export interface ExportFilesResult {
  /** 使用者選的資料夾；取消則 null */
  folder: string | null;
  results: ExportItemResult[];
}

export interface SaveFileResult {
  saved: boolean;
  /** 使用者選擇的路徑（取消時為 null） */
  path: string | null;
}

/**
 * Preload 透過 contextBridge 暴露給 Renderer 的「有限 API」（規格 §11-8）。
 * Renderer 只能呼叫這裡列出的方法，無法直接取得 Node.js / Electron 權限。
 */
export interface Mvr2tBridge {
  getAppInfo(): Promise<AppInfo>;
  getBackendState(): Promise<BackendState>;
  restartBackend(): Promise<BackendState>;
  /** 訂閱後端狀態變化；回傳取消訂閱函式。 */
  onBackendState(listener: (state: BackendState) => void): () => void;
  /** 程式不是目前使用中的視窗時，顯示系統通知並閃爍工作列圖示。回傳是否真的顯示了通知。 */
  notify(notification: AppNotification): Promise<boolean>;
  /** true：處理中，防止電腦因閒置自動睡眠（螢幕仍可關閉）；false：解除。 */
  setKeepAwake(on: boolean): Promise<void>;
  /** 跳出「另存新檔」對話框並寫入檔案；使用者取消時 saved = false。 */
  saveFile(request: SaveFileRequest): Promise<SaveFileResult>;
  /** 匯出面板：選資料夾並寫入多個檔案（Phase 08） */
  exportFiles(request: ExportFilesRequest): Promise<ExportFilesResult>;
  /** 開啟最近一次匯出的資料夾 */
  openExportFolder(): Promise<void>;
  /** 匯出資料夾偏好 */
  getExportPrefs(): Promise<ExportPrefs>;
  /** 跳出對話框選擇固定匯出資料夾；取消則不變 */
  chooseFixedExportFolder(): Promise<ExportPrefs>;
  /** 取消固定資料夾（匯出時改為每次詢問） */
  clearFixedExportFolder(): Promise<ExportPrefs>;
}
