import { create } from 'zustand';
import type { MindNode } from '@/features/mindmap/model';
import type {
  ExtractAudioResult,
  MediaInfo,
  SummarizeResult,
  Summary,
  TaskStatus,
  TranscribeResult,
  Transcript,
} from '@shared/types/api';

/**
 * 本次工作階段的狀態（只在記憶體中）。
 * 刻意不使用 persist middleware：媒體、逐字稿等資料不得被保存（PROJECT_SPEC §8.3），重新整理即清空。
 */

/** 匯入的來源：本機檔案（File 也符合）或 YouTube 下載的音訊（名稱 = 影片標題）。 */
export interface ImportSource {
  name: string;
  size: number;
}

export type ImportState =
  | { status: 'idle' }
  /** 正在把檔案內容複製到後端的 Session 暫存。 */
  | { status: 'uploading'; file: ImportSource; progress: number }
  /** 已複製完成，後端正在用 ffprobe 檢查檔案。 */
  | { status: 'probing'; file: ImportSource }
  | { status: 'ready'; file: ImportSource; info: MediaInfo }
  | { status: 'error'; file: ImportSource | null; message: string };

/** 一個背景工作（抽取音訊、語音辨識…）在畫面上的狀態。 */
export interface TaskTrack<TResult> {
  taskId: string | null;
  status: 'idle' | 'starting' | TaskStatus;
  progress: number;
  stage: string;
  detail: string;
  message: string | null;
  result: TResult | null;
}

export type ExtractionState = TaskTrack<ExtractAudioResult>;
export type TranscriptionState = TaskTrack<TranscribeResult>;
export type SummaryState = TaskTrack<SummarizeResult>;

const idle = <T,>(): TaskTrack<T> => ({
  taskId: null,
  status: 'idle',
  progress: 0,
  stage: '',
  detail: '',
  message: null,
  result: null,
});

export const idleExtraction: ExtractionState = idle<ExtractAudioResult>();
export const idleTranscription: TranscriptionState = idle<TranscribeResult>();
export const idleSummary: SummaryState = idle<SummarizeResult>();

interface SessionState {
  /** 後端的 Session ID；後端重新啟動（網址或憑證改變）時會重建。 */
  sessionId: string | null;
  /** 建立 sessionId 時所連的後端，用來偵測後端是否換了一個行程。 */
  backendKey: string | null;
  import: ImportState;
  extraction: ExtractionState;
  transcription: TranscriptionState;
  /** 本次 Session 的逐字稿（只在記憶體中，規格 §8.3） */
  transcript: Transcript | null;
  summarizing: SummaryState;
  /** 本次 Session 的摘要（只在記憶體中，規格 §8.3） */
  summary: Summary | null;
  /** 可編輯的心智圖（由摘要的心智圖建立，之後的編輯只在記憶體中，§8.3） */
  mindmap: MindNode | null;
  set: (
    patch: Partial<
      Pick<
        SessionState,
        'sessionId' | 'backendKey' | 'import' | 'extraction' | 'transcription' | 'transcript' | 'summarizing' | 'summary' | 'mindmap'
      >
    >,
  ) => void;
  patchExtraction: (patch: Partial<ExtractionState>) => void;
  patchTranscription: (patch: Partial<TranscriptionState>) => void;
  patchSummarizing: (patch: Partial<SummaryState>) => void;
  resetMedia: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  backendKey: null,
  import: { status: 'idle' },
  extraction: idleExtraction,
  transcription: idleTranscription,
  transcript: null,
  summarizing: idleSummary,
  summary: null,
  mindmap: null,
  set: (patch) => set(patch),
  patchExtraction: (patch) => set((s) => ({ extraction: { ...s.extraction, ...patch } })),
  patchTranscription: (patch) => set((s) => ({ transcription: { ...s.transcription, ...patch } })),
  patchSummarizing: (patch) => set((s) => ({ summarizing: { ...s.summarizing, ...patch } })),
  resetMedia: () =>
    set({
      import: { status: 'idle' },
      extraction: idleExtraction,
      transcription: idleTranscription,
      transcript: null,
      summarizing: idleSummary,
      summary: null,
      mindmap: null,
    }),
}));
