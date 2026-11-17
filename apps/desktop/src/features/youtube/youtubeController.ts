/**
 * YouTube 連結（使用者決定 2026-11-15）：讀取影片資訊 → 只下載音訊（＋可選的作者字幕）→ 與本機檔案相同的流程。
 * 狀態只在記憶體中（規格 §8.3）；「已同意使用說明」存在 Main 的 preferences.json。
 */
import { create } from 'zustand';
import type { SubtitleChoice, Transcript, YouTubeDownloadResult, YouTubeVideo, YtDlpState } from '@shared/types/api';
import { parseYouTubeUrl } from '@/lib/youtube';
import {
  ApiError,
  AbortedError,
  cancelTask,
  getBackendConnection,
  getTask,
  getTranscript,
  getYtDlp,
  probeYouTube,
  startYouTubeDownload,
  type BackendConnection,
} from '@/services/api';
import { beginExternalImport, ensureSession, finishExternalImport, setExternalImportCanceller } from '@/features/media/mediaController';
import { useSessionStore } from '@/stores/sessionStore';

const POLL_MS = 400;
const RECONNECT_MS = 2000;
const MAX_RECONNECT_ATTEMPTS = 150;

export type YouTubePhase = 'idle' | 'probing' | 'ready' | 'starting' | 'downloading' | 'error';

interface YouTubeState {
  component: YtDlpState | null;
  /** null = 還不知道；false = 需要先顯示使用說明 */
  noticeAccepted: boolean | null;
  phase: YouTubePhase;
  url: string;
  video: YouTubeVideo | null;
  taskId: string | null;
  progress: number;
  stage: string;
  detail: string;
  message: string | null;
  set: (patch: Partial<Omit<YouTubeState, 'set'>>) => void;
}

export const useYouTubeStore = create<YouTubeState>((set) => ({
  component: null,
  noticeAccepted: null,
  phase: 'idle',
  url: '',
  video: null,
  taskId: null,
  progress: 0,
  stage: '',
  detail: '',
  message: null,
  set: (patch) => set(patch),
}));

const ys = () => useYouTubeStore.getState();
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let probeController: AbortController | null = null;
/** 一般瀏覽器預覽（沒有 Electron）時，同意只記在記憶體 */
let browserNotice = false;

/** Electron 的橋接（一般瀏覽器預覽與測試時沒有）。 */
const bridge = () => (typeof window !== 'undefined' ? window.mvr2t : undefined);

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return '發生未預期的錯誤，請再試一次。';
}

async function connection(): Promise<BackendConnection> {
  const conn = await getBackendConnection();
  if (!conn) throw new ApiError(0, '本機後端尚未就緒，請稍候再試。');
  return conn;
}

function stopPolling(): void {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

/** 讀取元件狀態與「是否已同意使用說明」。 */
export async function loadYouTubeStatus(): Promise<void> {
  try {
    const b = bridge();
    const accepted = b ? await b.getYouTubeNotice() : browserNotice;
    ys().set({ noticeAccepted: accepted });
  } catch {
    ys().set({ noticeAccepted: false });
  }
  try {
    ys().set({ component: await getYtDlp(await connection()) });
  } catch {
    // 後端尚未就緒：畫面顯示「讀取中」，稍後再試
  }
}

export async function acceptYouTubeNotice(): Promise<void> {
  const b = bridge();
  if (b) await b.acceptYouTubeNotice();
  else browserNotice = true;
  ys().set({ noticeAccepted: true });
}

export function setYouTubeUrl(url: string): void {
  const s = ys();
  if (s.phase === 'downloading' || s.phase === 'starting') return;
  s.set({ url, ...(s.phase === 'ready' || s.phase === 'error' ? { phase: 'idle', video: null, message: null } : { message: null }) });
}

/** 讀取影片資訊（標題、長度、作者上傳的字幕）。 */
export async function probeVideo(): Promise<void> {
  const { url } = ys();
  if (!url.trim()) return ys().set({ phase: 'error', message: '請輸入 YouTube 網址。' });
  if (!parseYouTubeUrl(url)) return ys().set({ phase: 'error', message: '這不是有效的 YouTube 影片網址（只支援單一影片，不支援播放清單）。' });
  probeController?.abort();
  const controller = new AbortController();
  probeController = controller;
  ys().set({ phase: 'probing', video: null, message: null });
  try {
    const conn = await connection();
    const sessionId = await ensureSession(conn);
    const video = await probeYouTube(conn, sessionId, url, controller.signal);
    if (probeController !== controller) return;
    ys().set({ phase: 'ready', video });
  } catch (err) {
    if (probeController !== controller || err instanceof AbortedError) return;
    ys().set({ phase: 'error', message: messageOf(err) });
  } finally {
    if (probeController === controller) probeController = null;
  }
}

export function cancelProbe(): void {
  probeController?.abort();
  probeController = null;
  if (ys().phase === 'probing') ys().set({ phase: 'idle' });
}

/** 下載音訊；subtitle 不為 null 時一併下載作者字幕並直接當作逐字稿。 */
export async function downloadVideo(subtitle: SubtitleChoice | null): Promise<void> {
  const { video } = ys();
  if (!video) return;
  stopPolling();
  beginExternalImport();
  setExternalImportCanceller(() => void cancelDownload());
  ys().set({ phase: 'starting', taskId: null, progress: 0, stage: '準備中', detail: '', message: null });
  try {
    const conn = await connection();
    const sessionId = await ensureSession(conn);
    const { task_id } = await startYouTubeDownload(conn, sessionId, video, subtitle);
    // 後端已清除這個 Session 原本的媒體：畫面也回到「尚未匯入」，下載完成後換成 YouTube 的音訊
    useSessionStore.getState().resetMedia();
    ys().set({ phase: 'downloading', taskId: task_id });
    void poll(conn, sessionId, task_id, video);
  } catch (err) {
    setExternalImportCanceller(null);
    ys().set({ phase: 'error', message: messageOf(err) });
  }
}

async function poll(conn: BackendConnection, sessionId: string, taskId: string, video: YouTubeVideo, failures = 0): Promise<void> {
  const current = () => ys().taskId === taskId;
  try {
    const t = await getTask<YouTubeDownloadResult>(conn, sessionId, taskId);
    if (!current()) return;
    if (t.status === 'queued' || t.status === 'running') {
      ys().set({ progress: t.progress, stage: t.stage, detail: t.detail });
      pollTimer = setTimeout(() => void poll(conn, sessionId, taskId, video), POLL_MS);
      return;
    }
    setExternalImportCanceller(null);
    if (t.status === 'completed' && t.result) {
      const { media, subtitles } = t.result;
      let transcript: Transcript | null = null;
      if (subtitles) {
        try {
          transcript = await getTranscript(conn, sessionId, media.media_id);
        } catch {
          transcript = null; // 取不到時改用語音辨識
        }
      }
      if (!current()) return;
      finishExternalImport({ name: media.filename, size: media.size }, media, transcript);
      ys().set({ phase: 'idle', url: '', video: null, taskId: null, progress: 1, message: t.result.warnings[0] ?? null });
    } else if (t.status === 'cancelled') {
      ys().set({ phase: 'ready', taskId: null, message: '已取消下載。' });
    } else {
      ys().set({ phase: 'ready', taskId: null, message: t.message ?? 'YouTube 下載失敗。' });
    }
  } catch (err) {
    if (!current()) return;
    const network = err instanceof ApiError && err.status === 0;
    if (network && failures < MAX_RECONNECT_ATTEMPTS) {
      ys().set({ detail: '連線中斷，重新連線中…' });
      pollTimer = setTimeout(() => void poll(conn, sessionId, taskId, video, failures + 1), RECONNECT_MS);
      return;
    }
    setExternalImportCanceller(null);
    ys().set({ phase: 'error', taskId: null, message: messageOf(err) });
  }
}

export async function cancelDownload(): Promise<void> {
  const { taskId } = ys();
  const sessionId = useSessionStore.getState().sessionId;
  if (!taskId || !sessionId) return;
  ys().set({ stage: '正在取消' });
  try {
    await cancelTask(await connection(), sessionId, taskId);
  } catch {
    // 輪詢會回報最終狀態
  }
}

/** 測試用 */
export function __resetYouTubeForTests(): void {
  stopPolling();
  probeController = null;
  browserNotice = false;
  useYouTubeStore.setState({
    component: null,
    noticeAccepted: null,
    phase: 'idle',
    url: '',
    video: null,
    taskId: null,
    progress: 0,
    stage: '',
    detail: '',
    message: null,
  });
}
