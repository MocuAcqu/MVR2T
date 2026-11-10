import { useEffect } from 'react';
import type { AppNotification } from '@shared/types/ipc';
import { formatDuration } from '@/lib/format';
import { useSessionStore } from '@/stores/sessionStore';

type SessionSnapshot = ReturnType<typeof useSessionStore.getState>;

const ACTIVE = new Set(['starting', 'queued', 'running']);

/** 匯入、抽取音訊或語音辨識進行中 → 需要防止電腦自動睡眠。 */
export function isBusy(s: Pick<SessionSnapshot, 'import' | 'extraction' | 'transcription' | 'summarizing'>): boolean {
  return (
    s.import.status === 'uploading' ||
    s.import.status === 'probing' ||
    ACTIVE.has(s.extraction.status) ||
    ACTIVE.has(s.transcription.status) ||
    ACTIVE.has(s.summarizing.status)
  );
}

/** 語音辨識從「進行中」變成完成或失敗時的系統通知內容；其他變化不通知。 */
export function transcriptionNotification(
  prev: Pick<SessionSnapshot, 'transcription'>,
  next: Pick<SessionSnapshot, 'transcription' | 'transcript' | 'import'>,
): AppNotification | null {
  if (!ACTIVE.has(prev.transcription.status)) return null;
  const file = next.import.status === 'ready' ? next.import.info.filename : '';
  if (next.transcription.status === 'completed' && next.transcript) {
    const audio = next.transcription.result ? `，音訊 ${formatDuration(next.transcription.result.audio_seconds)}` : '';
    return { title: '逐字稿完成', body: `${file ? `${file}：` : ''}共 ${next.transcript.segments.length} 句${audio}。` };
  }
  if (next.transcription.status === 'failed') {
    return { title: '語音辨識失敗', body: next.transcription.message ?? '請回到 MVR2T 查看原因。' };
  }
  return null;
}

/** 摘要從「進行中」變成完成或失敗時的系統通知內容。 */
export function summaryNotification(
  prev: Pick<SessionSnapshot, 'summarizing'>,
  next: Pick<SessionSnapshot, 'summarizing' | 'summary' | 'import'>,
): AppNotification | null {
  if (!ACTIVE.has(prev.summarizing.status)) return null;
  const file = next.import.status === 'ready' ? next.import.info.filename : '';
  if (next.summarizing.status === 'completed' && next.summary) {
    return { title: '摘要完成', body: `${file ? `${file}：` : ''}已產生 ${next.summary.types.length} 種摘要內容。` };
  }
  if (next.summarizing.status === 'failed') {
    return { title: '摘要失敗', body: next.summarizing.message ?? '請回到 MVR2T 查看原因。' };
  }
  return null;
}

/**
 * 背景工作的副作用（在 App 最外層掛一次）：
 * - 處理中請 Electron 防止電腦自動睡眠，結束後解除
 * - 逐字稿或摘要完成／失敗時，若程式不在前景就顯示系統通知（由 Main 判斷）
 */
export function useBackgroundTaskEffects(): void {
  useEffect(() => {
    const bridge = window.mvr2t;
    if (!bridge) return; // 瀏覽器預覽：沒有通知與電源控制
    let awake = false;
    const sync = (s: SessionSnapshot) => {
      const busy = isBusy(s);
      if (busy !== awake) {
        awake = busy;
        void bridge.setKeepAwake(busy).catch(() => undefined);
      }
    };
    sync(useSessionStore.getState());
    const unsubscribe = useSessionStore.subscribe((s, prev) => {
      sync(s);
      for (const n of [transcriptionNotification(prev, s), summaryNotification(prev, s)]) {
        if (n) void bridge.notify(n).catch(() => undefined);
      }
    });
    return () => {
      unsubscribe();
      if (awake) void bridge.setKeepAwake(false).catch(() => undefined);
    };
  }, []);
}
