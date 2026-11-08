/**
 * 媒體匯入與音訊抽取的流程控制（Phase 04）。
 * 元件只呼叫這裡的函式；這裡負責呼叫 services/api 並更新 sessionStore。
 */
import { getMediaKind, MAX_MEDIA_BYTES, MEDIA_EXTENSIONS } from '@shared/constants/media';
import type { ExtractAudioResult } from '@shared/types/api';
import { formatBytes } from '@/lib/format';
import {
  AbortedError,
  ApiError,
  cancelTask,
  createSession,
  getBackendConnection,
  getTask,
  startExtraction as apiStartExtraction,
  uploadMedia,
  type BackendConnection,
} from '@/services/api';
import { idleExtraction, useSessionStore } from '@/stores/sessionStore';

const POLL_MS = 400;
const store = () => useSessionStore.getState();

let uploadController: AbortController | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let sessionPromise: Promise<string> | null = null;

const keyOf = (conn: BackendConnection) => `${conn.url}|${conn.token ?? ''}`;

async function connection(): Promise<BackendConnection> {
  const conn = await getBackendConnection();
  if (!conn) throw new ApiError(0, '本機後端尚未就緒，請稍候再試。');
  return conn;
}

function stopPolling(): void {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

/**
 * 確保有一個屬於「目前這個後端行程」的 Session。
 * 後端重新啟動後舊 Session 已不存在，所以清空畫面上的媒體狀態並重建。
 */
export async function ensureSession(conn: BackendConnection): Promise<string> {
  const key = keyOf(conn);
  const { sessionId, backendKey } = store();
  if (sessionId && backendKey === key) return sessionId;
  if (!sessionPromise) {
    sessionPromise = (async () => {
      if (backendKey && backendKey !== key) {
        // 後端換了一個行程：之前的檔案與工作都已不在
        stopPolling();
        uploadController?.abort();
        store().resetMedia();
      }
      const { session_id } = await createSession(conn);
      store().set({ sessionId: session_id, backendKey: key });
      return session_id;
    })().finally(() => {
      sessionPromise = null;
    });
  }
  return sessionPromise;
}

/** 前端先做格式與大小檢查（後端會再檢查一次）。回傳錯誤訊息或 null。 */
export function validateFile(file: File): string | null {
  if (!getMediaKind(file.name)) {
    const list = MEDIA_EXTENSIONS.map((e) => e.toUpperCase()).join('、');
    return `不支援這個檔案格式。請選擇 ${list} 其中一種。`;
  }
  if (file.size === 0) return '這個檔案是空的。';
  if (file.size > MAX_MEDIA_BYTES) return `檔案太大（${formatBytes(file.size)}）。上限為 ${formatBytes(MAX_MEDIA_BYTES)}。`;
  return null;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return '發生未預期的錯誤，請再試一次。';
}

export async function importFile(file: File): Promise<void> {
  const invalid = validateFile(file);
  if (invalid) {
    store().set({ import: { status: 'error', file, message: invalid } });
    return;
  }
  cancelImport();
  stopPolling();
  const controller = new AbortController();
  uploadController = controller;
  store().set({ import: { status: 'uploading', file, progress: 0 }, extraction: idleExtraction });

  try {
    const conn = await connection();
    const sessionId = await ensureSession(conn);
    const info = await uploadMedia(
      conn,
      sessionId,
      file,
      (progress) => {
        if (uploadController !== controller) return;
        store().set({ import: progress >= 1 ? { status: 'probing', file } : { status: 'uploading', file, progress } });
      },
      controller.signal,
    );
    if (uploadController !== controller) return;
    store().set({ import: { status: 'ready', file, info } });
  } catch (err) {
    if (uploadController !== controller) return;
    if (err instanceof AbortedError) store().resetMedia();
    else store().set({ import: { status: 'error', file, message: messageOf(err) } });
  } finally {
    if (uploadController === controller) uploadController = null;
  }
}

/** 取消正在進行的上傳（後端會刪除已寫入的部分）。 */
export function cancelImport(): void {
  const c = uploadController;
  uploadController = null;
  if (!c) return;
  c.abort();
  // 先清掉 uploadController 是為了讓 importFile 的 catch 忽略這次的中止；
  // 所以畫面要在這裡自己回到初始狀態，否則會停在「正在複製」的進度條（Windows 驗收發現）。
  // importFile 開始新上傳時也會呼叫這裡，緊接著就會把狀態設成新檔案的 uploading。
  store().resetMedia();
}

/** 移除目前的媒體：開一個新的 Session，後端會刪除舊 Session 的所有暫存檔。 */
export async function removeMedia(): Promise<void> {
  cancelImport();
  stopPolling();
  store().resetMedia();
  try {
    const conn = await connection();
    const { session_id } = await createSession(conn);
    store().set({ sessionId: session_id, backendKey: keyOf(conn) });
  } catch {
    // 後端不在時無須處理：下次匯入會重新建立 Session
  }
}

async function poll(conn: BackendConnection, sessionId: string, taskId: string): Promise<void> {
  try {
    const t = await getTask<ExtractAudioResult>(conn, sessionId, taskId);
    if (store().extraction.taskId !== taskId) return;
    store().patchExtraction({
      status: t.status,
      progress: t.progress,
      stage: t.stage,
      detail: t.detail,
      message: t.message,
      result: t.result,
    });
    if (t.status === 'queued' || t.status === 'running') pollTimer = setTimeout(() => void poll(conn, sessionId, taskId), POLL_MS);
  } catch (err) {
    if (store().extraction.taskId !== taskId) return;
    store().patchExtraction({ status: 'failed', message: messageOf(err) });
  }
}

export async function startExtraction(): Promise<void> {
  const state = store();
  if (state.import.status !== 'ready' || !state.sessionId) return;
  const mediaId = state.import.info.media_id;
  stopPolling();
  store().set({ extraction: { ...idleExtraction, status: 'starting', stage: '準備中' } });
  try {
    const conn = await connection();
    const { task_id } = await apiStartExtraction(conn, state.sessionId, mediaId);
    store().patchExtraction({ taskId: task_id, status: 'running' });
    void poll(conn, state.sessionId, task_id);
  } catch (err) {
    store().patchExtraction({ status: 'failed', message: messageOf(err) });
  }
}

export async function cancelExtraction(): Promise<void> {
  const { sessionId, extraction } = store();
  if (!sessionId || !extraction.taskId) return;
  store().patchExtraction({ stage: '正在取消' });
  try {
    await cancelTask(await connection(), sessionId, extraction.taskId);
  } catch {
    // 輪詢會回報最終狀態
  }
}

/** 測試用：重設模組內部狀態。 */
export function __resetForTests(): void {
  stopPolling();
  uploadController = null;
  sessionPromise = null;
}
