/**
 * Default model registry (PROJECT_SPEC 5.1 / 5.3, rule 16: IDs live in ONE place).
 * Phase 09 extends this with download URLs, SHA-256 and versions.
 */
export type ModelKind = 'asr' | 'llm';

export interface ModelSpec {
  id: string; // local folder name under models/
  kind: ModelKind;
  displayName: string;
  role: string; // short label shown in the UI
  source: string; // official upstream repo
  sizeLabel?: string;
}

export const DEFAULT_MODELS: readonly ModelSpec[] = [
  {
    id: 'qwen3-asr-0.6b',
    kind: 'asr',
    displayName: 'Qwen3-ASR 0.6B',
    role: '語音辨識',
    source: 'Qwen/Qwen3-ASR-0.6B-hf',
  },
  {
    id: 'qwen3-4b-q4_k_m',
    kind: 'llm',
    displayName: 'Qwen3-4B Q4_K_M',
    role: '摘要與心智圖',
    source: 'Qwen/Qwen3-4B-GGUF',
    sizeLabel: '約 2.5 GB',
  },
];
