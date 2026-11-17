/**
 * Backend API client。
 * 之後所有後端呼叫（模型、媒體、ASR…）都集中在 services/，元件不直接 fetch。
 *
 * Phase 03：在 Electron 內，後端位址（動態連接埠）與一次性連線憑證都由 Main Process 提供；
 * 每個請求都帶 `Authorization: Bearer <token>`。
 * 在一般瀏覽器預覽時（沒有 window.mvr2t），改連手動啟動的開發用後端，不帶憑證。
 */
import { DEFAULT_BACKEND_URL } from '@shared/constants/app';
import type {
  AsrLanguage,
  FfmpegStatus,
  HealthResponse,
  MediaInfo,
  ModelManagerState,
  PackageId,
  SystemInfo,
  SessionResponse,
  TaskState,
  Transcript,
  Summary,
  SummaryType,
  SubtitleChoice,
  BackendSettings,
  StorageInfo,
  TranscriptSegment,
  YouTubeVideo,
  YtDlpState,
} from '@shared/types/api';
import type { AppInfo } from '@shared/types/ipc';

export interface BackendConnection {
  url: string;
  token: string | null;
}

/** 是否在 Electron 視窗內（preload 有注入橋接）。 */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && !!window.mvr2t;
}

/** 取得 Electron 提供的應用程式資訊；不在 Electron 內時回傳 null。 */
export async function getAppInfo(): Promise<AppInfo | null> {
  if (!window.mvr2t) return null;
  try {
    return await window.mvr2t.getAppInfo();
  } catch {
    return null;
  }
}

/** 瀏覽器預覽用的後端位址：VITE_BACKEND_URL，其次預設 127.0.0.1:8765。 */
export function browserFallbackConnection(): BackendConnection {
  return { url: import.meta.env.VITE_BACKEND_URL ?? DEFAULT_BACKEND_URL, token: null };
}

/** 取得目前可用的後端連線；Electron 內後端尚未就緒時回傳 null。 */
export async function getBackendConnection(): Promise<BackendConnection | null> {
  if (!window.mvr2t) return browserFallbackConnection();
  const state = await window.mvr2t.getBackendState();
  return state.phase === 'running' && state.url ? { url: state.url, token: state.token } : null;
}

/** 所有後端請求的共同入口：自動加上憑證標頭。 */
export async function backendFetch(conn: BackendConnection, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (conn.token) headers.set('Authorization', `Bearer ${conn.token}`);
  return fetch(`${conn.url}${path}`, { ...init, headers });
}

export async function fetchHealth(conn: BackendConnection, signal?: AbortSignal): Promise<HealthResponse> {
  const res = await backendFetch(conn, '/api/health', { signal });
  if (!res.ok) throw new Error(`Backend responded with HTTP ${res.status}`);
  return (await res.json()) as HealthResponse;
}

// ---------------------------------------------------------------------------
// Phase 04：Session、媒體匯入、音訊抽取、工作進度
// ---------------------------------------------------------------------------

/** 後端回傳的錯誤；message 已是給使用者看的繁體中文（FastAPI 的 detail）。 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 使用者取消（上傳或請求被中止）。 */
export class AbortedError extends Error {
  constructor() {
    super('已取消');
    this.name = 'AbortedError';
  }
}

function detailOf(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  return `後端回應錯誤（HTTP ${status}）。`;
}

async function apiJson<T>(conn: BackendConnection, path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await backendFetch(conn, path, init);
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new AbortedError();
    throw new ApiError(0, '無法連線到本機後端。');
  }
  if (res.status === 204) return undefined as T;
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailOf(body, res.status));
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const createSession = (conn: BackendConnection) =>
  apiJson<SessionResponse>(conn, '/api/session', { method: 'POST' });

export const endSession = (conn: BackendConnection, sessionId: string) =>
  apiJson<void>(conn, `/api/session/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });

export const getFfmpegStatus = (conn: BackendConnection, signal?: AbortSignal) =>
  apiJson<FfmpegStatus>(conn, '/api/system/ffmpeg', { signal });

export const startExtraction = (conn: BackendConnection, sessionId: string, mediaId: string) =>
  apiJson<{ task_id: string }>(conn, '/api/media/extract-audio', json({ session_id: sessionId, media_id: mediaId }));

export const getTask = <T>(conn: BackendConnection, sessionId: string, taskId: string) =>
  apiJson<TaskState<T>>(conn, `/api/tasks/${encodeURIComponent(taskId)}?session_id=${encodeURIComponent(sessionId)}`);

export const cancelTask = (conn: BackendConnection, sessionId: string, taskId: string) =>
  apiJson<TaskState>(conn, `/api/tasks/${encodeURIComponent(taskId)}/cancel?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
  });

/**
 * 把檔案內容串流上傳到 Session 暫存（= 複製一份）。
 * 使用 XMLHttpRequest 是因為 fetch 沒有「上傳進度」事件；Chromium 會直接從磁碟串流 File，不會整個讀進記憶體。
 */
export function uploadMedia(
  conn: BackendConnection,
  sessionId: string,
  file: File,
  onProgress: (fraction: number) => void,
  signal: AbortSignal,
): Promise<MediaInfo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url =
      `${conn.url}/api/media/upload?session_id=${encodeURIComponent(sessionId)}` +
      `&filename=${encodeURIComponent(file.name)}`;
    xhr.open('POST', url);
    if (conn.token) xhr.setRequestHeader('Authorization', `Bearer ${conn.token}`);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as MediaInfo);
      else reject(new ApiError(xhr.status, detailOf(xhr.response, xhr.status)));
    };
    xhr.onerror = () => reject(new ApiError(0, '上傳失敗：無法連線到本機後端。'));
    xhr.onabort = () => reject(new AbortedError());
    if (signal.aborted) return reject(new AbortedError());
    signal.addEventListener('abort', () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}

// ---------------------------------------------------------------------------
// Phase 05：模型與語音辨識
// ---------------------------------------------------------------------------

// Phase 10：硬體與運算裝置
export const getSystemInfo = (conn: BackendConnection, refresh = false, signal?: AbortSignal) =>
  apiJson<SystemInfo>(conn, `/api/system/info${refresh ? '?refresh=true' : ''}`, { signal });

// Phase 09：模型管理
export const getModels = (conn: BackendConnection, signal?: AbortSignal) =>
  apiJson<ModelManagerState>(conn, '/api/models', { signal });

export const modelAction = (conn: BackendConnection, pkg: PackageId, action: 'download' | 'verify' | 'cancel') =>
  apiJson<ModelManagerState>(conn, `/api/models/${pkg}/${action}`, { method: 'POST' });

export const downloadAllModels = (conn: BackendConnection) =>
  apiJson<ModelManagerState>(conn, '/api/models/download-all', { method: 'POST' });

export const deleteModelPackage = (conn: BackendConnection, pkg: PackageId) =>
  apiJson<void>(conn, `/api/models/${pkg}`, { method: 'DELETE' });

export const deleteUnusedModel = (conn: BackendConnection, key: string) =>
  apiJson<void>(conn, `/api/models/unused/${key.split('/').map(encodeURIComponent).join('/')}`, { method: 'DELETE' });

export const startTranscription = (conn: BackendConnection, sessionId: string, mediaId: string, language: AsrLanguage | null) =>
  apiJson<{ task_id: string }>(conn, '/api/asr/transcribe', json({ session_id: sessionId, media_id: mediaId, language }));

export const getTranscript = (conn: BackendConnection, sessionId: string, mediaId: string) =>
  apiJson<Transcript>(
    conn,
    `/api/transcript?session_id=${encodeURIComponent(sessionId)}&media_id=${encodeURIComponent(mediaId)}`,
  );

export const startSummary = (conn: BackendConnection, sessionId: string, mediaId: string, types: SummaryType[]) =>
  apiJson<{ task_id: string }>(conn, '/api/summary/generate', json({ session_id: sessionId, media_id: mediaId, types }));

export const startMindmap = (conn: BackendConnection, sessionId: string, mediaId: string) =>
  apiJson<{ task_id: string }>(conn, '/api/mindmap/generate', json({ session_id: sessionId, media_id: mediaId }));

export const getSummary = (conn: BackendConnection, sessionId: string, mediaId: string) =>
  apiJson<Summary>(conn, `/api/summary?session_id=${encodeURIComponent(sessionId)}&media_id=${encodeURIComponent(mediaId)}`);

// ---------------------------------------------------------------------------
// YouTube 連結（yt-dlp）
// ---------------------------------------------------------------------------

export const getYtDlp = (conn: BackendConnection, signal?: AbortSignal) =>
  apiJson<YtDlpState>(conn, '/api/youtube/component', { signal });

export const ytDlpAction = (conn: BackendConnection, action: 'install' | 'check' | 'cancel') =>
  apiJson<YtDlpState>(conn, `/api/youtube/component/${action}`, { method: 'POST' });

export const deleteYtDlp = (conn: BackendConnection) => apiJson<void>(conn, '/api/youtube/component', { method: 'DELETE' });

export const probeYouTube = (conn: BackendConnection, sessionId: string, url: string, signal?: AbortSignal) =>
  apiJson<YouTubeVideo>(conn, '/api/youtube/probe', { ...json({ session_id: sessionId, url }), signal });

export const startYouTubeDownload = (conn: BackendConnection, sessionId: string, video: YouTubeVideo, subtitle: SubtitleChoice | null) =>
  apiJson<{ task_id: string }>(
    conn,
    '/api/youtube/download',
    json({
      session_id: sessionId,
      url: video.url,
      title: video.title,
      duration: video.duration,
      audio_size: video.audio_size,
      subtitle,
    }),
  );

// ---------------------------------------------------------------------------
// 逐字稿編輯器、工作區播放器（規格 §2.1-D）、設定頁（§12.4）
// ---------------------------------------------------------------------------

export const updateTranscript = (conn: BackendConnection, sessionId: string, mediaId: string, segments: TranscriptSegment[]) =>
  apiJson<Transcript>(conn, '/api/transcript', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, media_id: mediaId, segments }),
  });

/** 播放器用的網址：<video>／<audio> 不能帶 Authorization 標頭，所以憑證放在網址上（只有這個路徑接受）。 */
export function mediaFileUrl(conn: BackendConnection, sessionId: string, mediaId: string, kind: 'original' | 'audio' = 'original'): string {
  const q = new URLSearchParams({ session_id: sessionId, media_id: mediaId, kind });
  if (conn.token) q.set('token', conn.token);
  return `${conn.url}/api/media/file?${q.toString()}`;
}

export const getBackendSettings = (conn: BackendConnection) => apiJson<BackendSettings>(conn, '/api/settings');

export const putBackendSettings = (conn: BackendConnection, value: BackendSettings) =>
  apiJson<BackendSettings>(conn, '/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  });

export const getStorageInfo = (conn: BackendConnection) => apiJson<StorageInfo>(conn, '/api/settings/storage');

export const cleanupStorage = (conn: BackendConnection) =>
  apiJson<{ freed_bytes: number }>(conn, '/api/settings/cleanup', { method: 'POST' });
