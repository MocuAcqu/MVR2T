/**
 * 逐字稿編輯器（規格 §2.1-D）：編輯文字、刪除句子、與下一句合併、復原；每次修改都存回後端（只存在本次 Session）。
 * 句子保留原本的編號（摘要與心智圖用編號連結到逐字稿）。
 */
import type { TranscriptSegment } from '@shared/types/api';
import { ApiError, getBackendConnection, updateTranscript } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';

export function editText(segments: TranscriptSegment[], id: number, text: string): TranscriptSegment[] {
  // 改了文字後，逐字的時間就對不上了 → 清掉（匯出 JSON 時不會有錯誤的逐字時間）
  return segments.map((s) => (s.id === id ? { ...s, text, words: s.text === text ? s.words : [] } : s));
}

export function deleteSegment(segments: TranscriptSegment[], id: number): TranscriptSegment[] {
  return segments.filter((s) => s.id !== id);
}

/** 與下一句合併：保留第一句的編號與開始時間，結束時間取第二句。 */
export function mergeWithNext(segments: TranscriptSegment[], id: number): TranscriptSegment[] {
  const i = segments.findIndex((s) => s.id === id);
  if (i < 0 || i >= segments.length - 1) return segments;
  const a = segments[i];
  const b = segments[i + 1];
  // 中文直接接上；英文等以空白分隔的語言補一個空白
  const joiner = /[A-Za-z0-9.,!?;:'")\]]$/.test(a.text.trim()) && /^[A-Za-z0-9("'[]/.test(b.text.trim()) ? ' ' : '';
  const merged: TranscriptSegment = {
    ...a,
    end: Math.max(a.end, b.end),
    text: `${a.text.trim()}${joiner}${b.text.trim()}`,
    timing: a.timing === 'aligned' && b.timing === 'aligned' ? 'aligned' : 'estimated',
    words: [...a.words, ...b.words],
  };
  return [...segments.slice(0, i), merged, ...segments.slice(i + 2)];
}

/** 存回後端；成功後更新畫面上的逐字稿，已有摘要時標示「摘要是依修改前的內容產生的」。 */
export async function saveSegments(segments: TranscriptSegment[]): Promise<void> {
  const state = useSessionStore.getState();
  if (state.import.status !== 'ready' || !state.sessionId) throw new ApiError(0, '工作階段已結束。');
  const conn = await getBackendConnection();
  if (!conn) throw new ApiError(0, '本機後端尚未就緒，請稍候再試。');
  const transcript = await updateTranscript(conn, state.sessionId, state.import.info.media_id, segments);
  const now = useSessionStore.getState();
  if (now.import.status !== 'ready' || now.import.info.media_id !== transcript.media_id) return;
  now.set({ transcript, ...(now.summary ? { summaryStale: true } : {}) });
}
