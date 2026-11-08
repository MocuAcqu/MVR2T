import { create } from 'zustand';
import type { ExtractAudioResult, MediaInfo, TaskStatus } from '@shared/types/api';

/**
 * 本次工作階段的狀態（只在記憶體中）。
 * 刻意不使用 persist middleware：媒體、逐字稿等資料不得被保存（PROJECT_SPEC §8.3），重新整理即清空。
 */

export type ImportState =
  | { status: 'idle' }
  /** 正在把檔案內容複製到後端的 Session 暫存。 */
  | { status: 'uploading'; file: File; progress: number }
  /** 已複製完成，後端正在用 ffprobe 檢查檔案。 */
  | { status: 'probing'; file: File }
  | { status: 'ready'; file: File; info: MediaInfo }
  | { status: 'error'; file: File | null; message: string };

export interface ExtractionState {
  taskId: string | null;
  status: 'idle' | 'starting' | TaskStatus;
  progress: number;
  stage: string;
  detail: string;
  message: string | null;
  result: ExtractAudioResult | null;
}

export const idleExtraction: ExtractionState = {
  taskId: null,
  status: 'idle',
  progress: 0,
  stage: '',
  detail: '',
  message: null,
  result: null,
};

interface SessionState {
  /** 後端的 Session ID；後端重新啟動（網址或憑證改變）時會重建。 */
  sessionId: string | null;
  /** 建立 sessionId 時所連的後端，用來偵測後端是否換了一個行程。 */
  backendKey: string | null;
  import: ImportState;
  extraction: ExtractionState;
  set: (patch: Partial<Pick<SessionState, 'sessionId' | 'backendKey' | 'import' | 'extraction'>>) => void;
  patchExtraction: (patch: Partial<ExtractionState>) => void;
  resetMedia: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  backendKey: null,
  import: { status: 'idle' },
  extraction: idleExtraction,
  set: (patch) => set(patch),
  patchExtraction: (patch) => set((s) => ({ extraction: { ...s.extraction, ...patch } })),
  resetMedia: () => set({ import: { status: 'idle' }, extraction: idleExtraction }),
}));
