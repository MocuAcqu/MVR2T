/** GET /api/health 回應（需與 apps/backend/app/schemas/health.py 保持一致）。 */
export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  platform: string;
  python_version: string;
}

// ---------------------------------------------------------------------------
// Phase 04（需與 apps/backend/app/schemas/media.py 保持一致）
// ---------------------------------------------------------------------------

export interface SessionResponse {
  session_id: string;
}

/** POST /api/media/upload 回應：後端以 ffprobe 實際讀取到的影音資訊。 */
export interface MediaInfo {
  media_id: string;
  filename: string;
  format: string; // 副檔名（小寫）
  kind: 'video' | 'audio';
  size: number; // bytes
  duration: number; // 秒
  container: string;
  audio_codec: string | null;
  sample_rate: number | null;
  channels: number | null;
  has_video: boolean;
  video_codec: string | null;
  width: number | null;
  height: number | null;
}

/** 切段結果：start / end 是「原始檔案」時間軸上的秒數。 */
export interface AudioSegment {
  index: number;
  start: number;
  end: number;
  duration: number;
  /** 這段結尾的切法：在停頓處切、找不到停頓時硬切（與下一段重疊）、或檔案結尾。 */
  boundary: 'silence' | 'hard' | 'end';
}

export interface ExtractAudioResult {
  media_id: string;
  sample_rate: number;
  channels: number;
  duration: number;
  silence_count: number;
  params: { target_seconds: number; window_seconds: number; min_seconds: number; overlap_seconds: number };
  segments: AudioSegment[];
}

export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface TaskState<TResult = unknown> {
  task_id: string;
  session_id: string;
  kind: string;
  status: TaskStatus;
  progress: number; // 0 ~ 1
  stage: string;
  detail: string;
  message: string | null;
  result: TResult | null;
}

export interface FfmpegStatus {
  available: boolean;
  version: string | null;
  source: 'settings' | 'app-runtime' | 'path' | 'winget' | null;
  ffmpeg_path: string | null;
}

// ---------------------------------------------------------------------------
// Phase 05（需與 apps/backend/app/schemas/media.py 保持一致）
// ---------------------------------------------------------------------------

export interface ModelInfo {
  id: string;
  kind: 'asr' | 'aligner' | 'llm';
  display_name: string;
  role: string;
  repo: string;
  revision: string;
  license: string;
  size_bytes: number;
  installed: boolean;
  downloadable: boolean;
  /** 尚未提供下載的模型會在哪個 Phase 推出 */
  available_from_phase: number | null;
}

export interface ModelsResponse {
  models_dir: string;
  models: ModelInfo[];
}

/** 可指定的辨識語言（Qwen3-ASR 的英文名稱）；null = 自動偵測 */
export type AsrLanguage = 'Chinese' | 'English' | 'Cantonese' | 'Japanese' | 'Korean';

export interface TranscriptWord {
  text: string;
  start: number;
  end: number;
}

/** 逐字稿的一句：start / end 是「原始檔案」時間軸上的秒數。 */
export interface TranscriptSegment {
  id: number;
  start: number;
  end: number;
  text: string;
  /** aligned = 對齊模型產生的精確時間；estimated = 依字數估計 */
  timing: 'aligned' | 'estimated';
  words: TranscriptWord[];
}

export interface Transcript {
  media_id: string;
  language: string | null;
  timing: 'aligned' | 'estimated' | 'mixed';
  duration: number;
  models: Record<string, string | null>;
  warnings: string[];
  segments: TranscriptSegment[];
}

/** 語音辨識工作完成時的摘要（完整逐字稿另以 GET /api/transcript 取得）。 */
export interface TranscribeResult {
  media_id: string;
  language: string | null;
  timing: Transcript['timing'];
  segment_count: number;
  warnings: string[];
  elapsed_seconds: number;
  audio_seconds: number;
}
