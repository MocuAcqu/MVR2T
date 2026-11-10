/**
 * 媒體匯入與音訊抽取的流程控制（Phase 04）。
 * 元件只呼叫這裡的函式；這裡負責呼叫 services/api 並更新 sessionStore。
 */
import { getMediaKind, MAX_MEDIA_BYTES, MEDIA_EXTENSIONS } from '@shared/constants/media';
import type { AsrLanguage, SummaryType } from '@shared/types/api';
import { formatBytes } from '@/lib/format';
import {
  AbortedError,
  ApiError,
  cancelTask,
  createSession,
  getBackendConnection,
  getSummary,
  getTask,
  getTranscript,
  startExtraction as apiStartExtraction,
  startMindmap as apiStartMindmap,
  startSummary as apiStartSummary,
  startTranscription as apiStartTranscription,
  uploadMedia,
  type BackendConnection,
} from '@/services/api';
import { fromSummary } from '@/features/mindmap/model';
import { idleExtraction, idleSummary, idleTranscription, useSessionStore } from '@/stores/sessionStore';

const POLL_MS = 400;
/**
 * 輪詢時連不到後端（例如電腦睡眠、喚醒的那一刻）不要立刻判定失敗：工作仍在後端進行。
 * 每 2 秒重試，連續失敗約 5 分鐘（以次數計，睡眠期間不算）才放棄。
 */
const RECONNECT_MS = 2000;
const MAX_RECONNECT_ATTEMPTS = 150;
const store = () => useSessionStore.getState();

let uploadController: AbortController | null = null;
type TrackKind = 'extraction' | 'transcription' | 'summarizing';
const pollTimers: Record<TrackKind, ReturnType<typeof setTimeout> | null> = {
  extraction: null,
  transcription: null,
  summarizing: null,
};
let sessionPromise: Promise<string> | null = null;

const keyOf = (conn: BackendConnection) => `${conn.url}|${conn.token ?? ''}`;

async function connection(): Promise<BackendConnection> {
  const conn = await getBackendConnection();
  if (!conn) throw new ApiError(0, '本機後端尚未就緒，請稍候再試。');
  return conn;
}

function stopPolling(kind?: TrackKind): void {
  for (const k of kind ? [kind] : (Object.keys(pollTimers) as TrackKind[])) {
    const t = pollTimers[k];
    if (t) clearTimeout(t);
    pollTimers[k] = null;
  }
}

const patchTrack = (kind: TrackKind, patch: Record<string, unknown>) =>
  kind === 'extraction'
    ? store().patchExtraction(patch)
    : kind === 'transcription'
      ? store().patchTranscription(patch)
      : store().patchSummarizing(patch);

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
  // 新檔案：舊檔案的所有工作狀態都要清掉（後端上傳時會取消舊工作）。否則正在進行的辨識或摘要會一直顯示「進行中」，
  // isBusy 也維持 true，防睡眠不會解除（2026-11-10 Windows 驗收：摘要中從首頁更換檔案）。
  store().set({
    import: { status: 'uploading', file, progress: 0 },
    extraction: idleExtraction,
    transcription: idleTranscription,
    transcript: null,
    summarizing: idleSummary,
    summary: null,
    mindmap: null,
  });

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

/** 輪詢一個背景工作直到結束；onCompleted 在成功完成時呼叫（例如取回完整逐字稿）。 */
async function poll(
  kind: TrackKind,
  conn: BackendConnection,
  sessionId: string,
  taskId: string,
  onCompleted?: () => Promise<void>,
  failures = 0,
): Promise<void> {
  const current = () => store()[kind].taskId === taskId;
  try {
    const t = await getTask<unknown>(conn, sessionId, taskId);
    if (!current()) return;
    if (t.status === 'completed' && onCompleted) await onCompleted();
    if (!current()) return;
    patchTrack(kind, {
      status: t.status,
      progress: t.progress,
      stage: t.stage,
      detail: t.detail,
      message: t.message,
      result: t.result,
    });
    if (t.status === 'queued' || t.status === 'running') {
      pollTimers[kind] = setTimeout(() => void poll(kind, conn, sessionId, taskId, onCompleted), POLL_MS);
    }
  } catch (err) {
    if (!current()) return;
    const network = err instanceof ApiError && err.status === 0;
    if (network && failures < MAX_RECONNECT_ATTEMPTS) {
      patchTrack(kind, { detail: '連線中斷，重新連線中…' });
      pollTimers[kind] = setTimeout(
        () => void poll(kind, conn, sessionId, taskId, onCompleted, failures + 1),
        RECONNECT_MS,
      );
      return;
    }
    patchTrack(kind, { status: 'failed', message: messageOf(err) });
  }
}

export async function startExtraction(): Promise<void> {
  const state = store();
  if (state.import.status !== 'ready' || !state.sessionId) return;
  const mediaId = state.import.info.media_id;
  stopPolling('extraction');
  // 重新抽取後，舊逐字稿的時間就不再對應（後端也會清除）；摘要依附在逐字稿上
  store().set({
    extraction: { ...idleExtraction, status: 'starting', stage: '準備中' },
    transcription: idleTranscription,
    transcript: null,
    summarizing: idleSummary,
    summary: null,
    mindmap: null,
  });
  try {
    const conn = await connection();
    const { task_id } = await apiStartExtraction(conn, state.sessionId, mediaId);
    store().patchExtraction({ taskId: task_id, status: 'running' });
    void poll('extraction', conn, state.sessionId, task_id);
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

// ---------------------------------------------------------------------------
// Phase 05：語音辨識
// ---------------------------------------------------------------------------

/** 開始語音辨識（需先完成抽取音訊）。language = null 為自動偵測。 */
export async function startTranscription(language: AsrLanguage | null): Promise<void> {
  const state = store();
  if (state.import.status !== 'ready' || !state.sessionId || state.extraction.status !== 'completed') return;
  const mediaId = state.import.info.media_id;
  const sessionId = state.sessionId;
  stopPolling('transcription');
  store().set({
    transcription: { ...idleTranscription, status: 'starting', stage: '準備中' },
    transcript: null,
    summarizing: idleSummary,
    summary: null,
    mindmap: null,
  });
  try {
    const conn = await connection();
    const { task_id } = await apiStartTranscription(conn, sessionId, mediaId, language);
    store().patchTranscription({ taskId: task_id, status: 'running' });
    void poll('transcription', conn, sessionId, task_id, async () => {
      const transcript = await getTranscript(conn, sessionId, mediaId);
      if (store().transcription.taskId === task_id) store().set({ transcript });
    });
  } catch (err) {
    store().patchTranscription({ status: 'failed', message: messageOf(err) });
  }
}

export async function cancelTranscription(): Promise<void> {
  const { sessionId, transcription } = store();
  if (!sessionId || !transcription.taskId) return;
  store().patchTranscription({ stage: '正在取消' });
  try {
    await cancelTask(await connection(), sessionId, transcription.taskId);
  } catch {
    // 輪詢會回報最終狀態
  }
}

// ---------------------------------------------------------------------------
// Phase 06：摘要
// ---------------------------------------------------------------------------

/** 依勾選的類型產生摘要（需先完成語音辨識）。 */
export async function startSummary(types: SummaryType[]): Promise<void> {
  const state = store();
  if (state.import.status !== 'ready' || !state.sessionId || !state.transcript || types.length === 0) return;
  const mediaId = state.import.info.media_id;
  const sessionId = state.sessionId;
  stopPolling('summarizing');
  store().set({ summarizing: { ...idleSummary, status: 'starting', stage: '準備中' }, summary: null, mindmap: null });
  try {
    const conn = await connection();
    const { task_id } = await apiStartSummary(conn, sessionId, mediaId, types);
    store().patchSummarizing({ taskId: task_id, status: 'running' });
    void poll('summarizing', conn, sessionId, task_id, () => fetchSummary(conn, sessionId, mediaId, task_id));
  } catch (err) {
    store().patchSummarizing({ status: 'failed', message: messageOf(err) });
  }
}

/** 取回摘要；有心智圖時建立可編輯的心智圖（取代之前的編輯）。 */
async function fetchSummary(conn: BackendConnection, sessionId: string, mediaId: string, taskId: string): Promise<void> {
  const summary = await getSummary(conn, sessionId, mediaId);
  if (store().summarizing.taskId !== taskId) return;
  const mm = summary.results.mindmap;
  store().set({ summary, mindmap: mm ? fromSummary(mm) : store().mindmap });
}

/** 只重新產生心智圖（保留其他摘要內容）。 */
export async function startMindmap(): Promise<void> {
  const state = store();
  if (state.import.status !== 'ready' || !state.sessionId || !state.transcript) return;
  const mediaId = state.import.info.media_id;
  const sessionId = state.sessionId;
  stopPolling('summarizing');
  store().set({ summarizing: { ...idleSummary, status: 'starting', stage: '準備中' } });
  try {
    const conn = await connection();
    const { task_id } = await apiStartMindmap(conn, sessionId, mediaId);
    store().patchSummarizing({ taskId: task_id, status: 'running' });
    void poll('summarizing', conn, sessionId, task_id, () => fetchSummary(conn, sessionId, mediaId, task_id));
  } catch (err) {
    store().patchSummarizing({ status: 'failed', message: messageOf(err) });
  }
}

export async function cancelSummary(): Promise<void> {
  const { sessionId, summarizing } = store();
  if (!sessionId || !summarizing.taskId) return;
  store().patchSummarizing({ stage: '正在取消' });
  try {
    await cancelTask(await connection(), sessionId, summarizing.taskId);
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
