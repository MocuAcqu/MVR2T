import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  createSession: vi.fn(),
  getBackendConnection: vi.fn(),
  uploadMedia: vi.fn(),
  startExtraction: vi.fn(),
  getTask: vi.fn(),
  cancelTask: vi.fn(),
  startTranscription: vi.fn(),
  getTranscript: vi.fn(),
  startSummary: vi.fn(),
  getSummary: vi.fn(),
}));

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ...actual, ...api };
});

import { AbortedError, ApiError } from '@/services/api';
import { MAX_MEDIA_BYTES } from '@shared/constants/media';
import { idleExtraction, idleTranscription, useSessionStore } from '@/stores/sessionStore';
import {
  __resetForTests,
  cancelImport,
  ensureSession,
  importFile,
  startExtraction,
  startSummary,
  startTranscription,
  validateFile,
} from '../mediaController';

const conn = { url: 'http://127.0.0.1:5000', token: 'a' };
const file = (name: string, size = 10) => ({ name, size }) as File;
const info = { media_id: 'm1', filename: 'a.mp4', duration: 12 } as never;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  __resetForTests();
  useSessionStore.setState({
    sessionId: null,
    backendKey: null,
    import: { status: 'idle' },
    extraction: idleExtraction,
    transcription: idleTranscription,
    transcript: null,
  });
  api.getBackendConnection.mockResolvedValue(conn);
  api.createSession.mockResolvedValue({ session_id: 's1' });
});

describe('validateFile', () => {
  it('accepts supported media', () => {
    expect(validateFile(file('talk.MP3'))).toBeNull();
  });
  it('rejects unsupported formats, empty and oversized files', () => {
    expect(validateFile(file('notes.pdf'))).toContain('不支援');
    expect(validateFile(file('a.mp4', 0))).toContain('空的');
    expect(validateFile(file('a.mp4', MAX_MEDIA_BYTES + 1))).toContain('太大');
  });
});

describe('ensureSession', () => {
  it('creates one session per backend process and reuses it', async () => {
    expect(await ensureSession(conn)).toBe('s1');
    expect(await ensureSession(conn)).toBe('s1');
    expect(api.createSession).toHaveBeenCalledTimes(1);
  });

  it('concurrent callers share a single request', async () => {
    const [a, b] = await Promise.all([ensureSession(conn), ensureSession(conn)]);
    expect([a, b]).toEqual(['s1', 's1']);
    expect(api.createSession).toHaveBeenCalledTimes(1);
  });

  it('when the backend restarts, clears the old media and creates a new session', async () => {
    await ensureSession(conn);
    useSessionStore.setState({ import: { status: 'ready', file: file('a.mp4'), info } });
    api.createSession.mockResolvedValue({ session_id: 's2' });
    expect(await ensureSession({ url: 'http://127.0.0.1:6000', token: 'b' })).toBe('s2');
    expect(useSessionStore.getState().import.status).toBe('idle');
  });
});

describe('importFile', () => {
  it('rejects invalid files without contacting the backend', async () => {
    await importFile(file('notes.pdf'));
    expect(useSessionStore.getState().import).toMatchObject({ status: 'error' });
    expect(api.uploadMedia).not.toHaveBeenCalled();
  });

  it('uploads, reports progress, then stores the probed info', async () => {
    const seen: string[] = [];
    useSessionStore.subscribe((s) => seen.push(s.import.status));
    api.uploadMedia.mockImplementation(async (_c, _s, _f, onProgress: (n: number) => void) => {
      onProgress(0.5);
      onProgress(1);
      return info;
    });
    await importFile(file('a.mp4'));
    expect(api.uploadMedia).toHaveBeenCalledWith(conn, 's1', expect.anything(), expect.any(Function), expect.any(AbortSignal));
    expect(seen).toEqual(expect.arrayContaining(['uploading', 'probing', 'ready']));
    expect(useSessionStore.getState().import).toMatchObject({ status: 'ready', info });
  });

  it('shows the backend message on failure, and returns to idle on cancel', async () => {
    api.uploadMedia.mockRejectedValueOnce(new ApiError(422, '這個檔案沒有音訊軌，無法進行語音辨識。'));
    await importFile(file('a.mp4'));
    expect(useSessionStore.getState().import).toMatchObject({ status: 'error', message: expect.stringContaining('沒有音訊軌') });

    api.uploadMedia.mockRejectedValueOnce(new AbortedError());
    await importFile(file('a.mp4'));
    expect(useSessionStore.getState().import.status).toBe('idle');
  });
});

describe('cancelImport', () => {
  /** uploadMedia that reports progress, then waits until its AbortSignal fires (like a real XHR). */
  const pendingUpload = (progress: number) =>
    api.uploadMedia.mockImplementationOnce(
      (_c, _s, _f, onProgress: (n: number) => void, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          if (signal.aborted) return reject(new AbortedError()); // same as the real uploadMedia
          onProgress(progress);
          signal.addEventListener('abort', () => reject(new AbortedError()), { once: true });
        }),
    );

  it('pressing Cancel mid-upload returns the UI to idle (regression: it stayed on the progress bar)', async () => {
    pendingUpload(0.15);
    const running = importFile(file('big.mp4'));
    await vi.waitFor(() => expect(useSessionStore.getState().import).toMatchObject({ status: 'uploading', progress: 0.15 }));
    cancelImport();
    await running;
    expect(useSessionStore.getState().import.status).toBe('idle');
  });

  it('choosing another file mid-upload shows the new file, not idle', async () => {
    pendingUpload(0.3);
    const first = importFile(file('first.mp4'));
    // wait until the first upload is really in flight (progress reported), not just marked as uploading
    await vi.waitFor(() => expect(useSessionStore.getState().import).toMatchObject({ status: 'uploading', progress: 0.3 }));
    api.uploadMedia.mockResolvedValueOnce(info);
    await importFile(file('second.mp4'));
    await first;
    const state = useSessionStore.getState().import;
    expect(state.status).toBe('ready');
    expect(state.status === 'ready' && state.file.name).toBe('second.mp4');
  });

  it('is a no-op when nothing is uploading', () => {
    useSessionStore.setState({ import: { status: 'ready', file: file('a.mp4'), info } });
    cancelImport();
    expect(useSessionStore.getState().import.status).toBe('ready');
  });
});

describe('startExtraction', () => {
  it('polls the task until it completes', async () => {
    vi.useFakeTimers();
    useSessionStore.setState({ sessionId: 's1', backendKey: `${conn.url}|a`, import: { status: 'ready', file: file('a.mp4'), info } });
    api.startExtraction.mockResolvedValue({ task_id: 't1' });
    api.getTask
      .mockResolvedValueOnce({ status: 'running', progress: 0.4, stage: '正在抽取音訊', detail: '', message: null, result: null })
      .mockResolvedValueOnce({ status: 'completed', progress: 1, stage: '完成', detail: '', message: null, result: { segments: [] } });
    await startExtraction();
    await vi.advanceTimersByTimeAsync(0);
    expect(useSessionStore.getState().extraction).toMatchObject({ status: 'running', progress: 0.4 });
    await vi.advanceTimersByTimeAsync(500);
    expect(useSessionStore.getState().extraction).toMatchObject({ status: 'completed', progress: 1 });
    expect(api.getTask).toHaveBeenCalledWith(conn, 's1', 't1');
  });
  it('keeps waiting when the backend is briefly unreachable (e.g. the computer slept) instead of failing', async () => {
    vi.useFakeTimers();
    useSessionStore.setState({ sessionId: 's1', backendKey: `${conn.url}|a`, import: { status: 'ready', file: file('a.mp4'), info } });
    api.startExtraction.mockResolvedValue({ task_id: 't1' });
    api.getTask
      .mockResolvedValueOnce({ status: 'running', progress: 0.4, stage: '正在抽取音訊', detail: '', message: null, result: null })
      .mockRejectedValueOnce(new ApiError(0, '無法連線到本機後端。'))
      .mockRejectedValueOnce(new ApiError(0, '無法連線到本機後端。'))
      .mockResolvedValueOnce({ status: 'completed', progress: 1, stage: '完成', detail: '', message: null, result: { segments: [] } });
    await startExtraction();
    await vi.advanceTimersByTimeAsync(500);
    expect(useSessionStore.getState().extraction).toMatchObject({ status: 'running', progress: 0.4, detail: '連線中斷，重新連線中…' });
    await vi.advanceTimersByTimeAsync(4100);
    expect(useSessionStore.getState().extraction).toMatchObject({ status: 'completed', detail: '' });
  });

  it('still fails right away on a real error from the backend', async () => {
    vi.useFakeTimers();
    useSessionStore.setState({ sessionId: 's1', backendKey: `${conn.url}|a`, import: { status: 'ready', file: file('a.mp4'), info } });
    api.startExtraction.mockResolvedValue({ task_id: 't1' });
    api.getTask.mockRejectedValueOnce(new ApiError(404, '找不到這個工作。'));
    await startExtraction();
    await vi.advanceTimersByTimeAsync(0);
    expect(useSessionStore.getState().extraction).toMatchObject({ status: 'failed', message: '找不到這個工作。' });
  });
});

describe('startTranscription', () => {
  const ready = (extractionStatus: 'completed' | 'idle') =>
    useSessionStore.setState({
      sessionId: 's1',
      backendKey: `${conn.url}|a`,
      import: { status: 'ready', file: file('a.mp4'), info },
      extraction: { ...idleExtraction, status: extractionStatus },
    });

  it('does nothing until audio extraction has completed', async () => {
    ready('idle');
    await startTranscription(null);
    expect(api.startTranscription).not.toHaveBeenCalled();
  });

  it('polls the task and fetches the full transcript when it completes', async () => {
    vi.useFakeTimers();
    ready('completed');
    const transcript = { media_id: 'm1', language: 'Chinese', timing: 'aligned', segments: [{ id: 0, text: '你好。' }] };
    api.startTranscription.mockResolvedValue({ task_id: 't9' });
    api.getTask
      .mockResolvedValueOnce({ status: 'running', progress: 0.3, stage: '正在辨識語音', detail: '第 1 / 2 段', message: null, result: null })
      .mockResolvedValueOnce({ status: 'completed', progress: 1, stage: '完成', detail: '', message: null, result: { segment_count: 1 } });
    api.getTranscript.mockResolvedValue(transcript);
    await startTranscription('Chinese');
    expect(api.startTranscription).toHaveBeenCalledWith(conn, 's1', 'm1', 'Chinese');
    await vi.advanceTimersByTimeAsync(0);
    expect(useSessionStore.getState().transcription).toMatchObject({ status: 'running', detail: '第 1 / 2 段' });
    expect(useSessionStore.getState().transcript).toBeNull();
    await vi.advanceTimersByTimeAsync(500);
    expect(api.getTranscript).toHaveBeenCalledWith(conn, 's1', 'm1');
    expect(useSessionStore.getState().transcription.status).toBe('completed');
    expect(useSessionStore.getState().transcript).toEqual(transcript);
  });

  it('shows the backend message when it cannot start (e.g. model not downloaded)', async () => {
    ready('completed');
    api.startTranscription.mockRejectedValue(new ApiError(412, '尚未下載語音辨識模型。'));
    await startTranscription(null);
    expect(useSessionStore.getState().transcription).toMatchObject({ status: 'failed', message: '尚未下載語音辨識模型。' });
  });

  it('re-extracting audio clears the old transcript', async () => {
    ready('completed');
    useSessionStore.setState({ transcript: { media_id: 'm1' } as never });
    api.startExtraction.mockResolvedValue({ task_id: 'x1' });
    api.getTask.mockResolvedValue({ status: 'running', progress: 0, stage: '', detail: '', message: null, result: null });
    await startExtraction();
    expect(useSessionStore.getState().transcript).toBeNull();
  });
});

describe('startSummary', () => {
  const transcribed = () =>
    useSessionStore.setState({
      sessionId: 's1',
      backendKey: `${conn.url}|a`,
      import: { status: 'ready', file: file('a.mp4'), info },
      extraction: { ...idleExtraction, status: 'completed' },
      transcription: { ...idleTranscription, status: 'completed' },
      transcript: { media_id: 'm1', segments: [{ id: 0, text: '你好' }] } as never,
    });

  it('does nothing without a transcript or without any type', async () => {
    await startSummary(['overview']);
    transcribed();
    await startSummary([]);
    expect(api.startSummary).not.toHaveBeenCalled();
  });

  it('polls the task and fetches the summary when it completes', async () => {
    vi.useFakeTimers();
    transcribed();
    const summary = { media_id: 'm1', types: ['overview'], results: { overview: '摘要' } };
    api.startSummary.mockResolvedValue({ task_id: 'sum1' });
    api.getTask
      .mockResolvedValueOnce({ status: 'running', progress: 0, stage: '正在載入摘要模型', detail: '', message: null, result: null })
      .mockResolvedValueOnce({ status: 'completed', progress: 1, stage: '完成', detail: '', message: null, result: { types: ['overview'] } });
    api.getSummary.mockResolvedValue(summary);
    await startSummary(['overview', 'qa']);
    expect(api.startSummary).toHaveBeenCalledWith(conn, 's1', 'm1', ['overview', 'qa']);
    await vi.advanceTimersByTimeAsync(0);
    expect(useSessionStore.getState().summarizing.stage).toBe('正在載入摘要模型');
    await vi.advanceTimersByTimeAsync(500);
    expect(useSessionStore.getState().summarizing.status).toBe('completed');
    expect(useSessionStore.getState().summary).toEqual(summary);
  });

  it('re-transcribing clears the old summary', async () => {
    transcribed();
    useSessionStore.setState({ summary: { media_id: 'm1' } as never });
    api.startTranscription.mockResolvedValue({ task_id: 't2' });
    api.getTask.mockResolvedValue({ status: 'running', progress: 0, stage: '', detail: '', message: null, result: null });
    await startTranscription(null);
    expect(useSessionStore.getState().summary).toBeNull();
  });
});
