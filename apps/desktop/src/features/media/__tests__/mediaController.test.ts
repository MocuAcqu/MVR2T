import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  createSession: vi.fn(),
  getBackendConnection: vi.fn(),
  uploadMedia: vi.fn(),
  startExtraction: vi.fn(),
  getTask: vi.fn(),
  cancelTask: vi.fn(),
}));

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ...actual, ...api };
});

import { AbortedError, ApiError } from '@/services/api';
import { MAX_MEDIA_BYTES } from '@shared/constants/media';
import { idleExtraction, useSessionStore } from '@/stores/sessionStore';
import { __resetForTests, cancelImport, ensureSession, importFile, startExtraction, validateFile } from '../mediaController';

const conn = { url: 'http://127.0.0.1:5000', token: 'a' };
const file = (name: string, size = 10) => ({ name, size }) as File;
const info = { media_id: 'm1', filename: 'a.mp4', duration: 12 } as never;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  __resetForTests();
  useSessionStore.setState({ sessionId: null, backendKey: null, import: { status: 'idle' }, extraction: idleExtraction });
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

  /** Upload mock that reports some progress, then waits until its signal is aborted (like the real XHR). */
  const hangingUpload = () =>
    api.uploadMedia.mockImplementationOnce(
      (_c, _s, _f, onProgress: (n: number) => void, signal: AbortSignal) =>
        new Promise((_resolve, reject) => {
          onProgress(0.15);
          signal.addEventListener('abort', () => reject(new AbortedError()), { once: true });
        }),
    );
  const uploadStarted = () => vi.waitFor(() => expect(api.uploadMedia).toHaveBeenCalled());

  it('returns to idle when the user presses Cancel during upload (regression: stuck at 15%)', async () => {
    hangingUpload();
    const pending = importFile(file('a.mp4'));
    await uploadStarted();
    expect(useSessionStore.getState().import).toMatchObject({ status: 'uploading', progress: 0.15 });

    cancelImport();
    await pending;
    expect(useSessionStore.getState().import.status).toBe('idle');
  });

  it('keeps showing the new file when another file is picked during upload', async () => {
    hangingUpload();
    const first = importFile(file('first.mp4'));
    await uploadStarted();

    api.uploadMedia.mockResolvedValueOnce(info);
    await importFile(file('second.mp4'));
    await first;
    expect(useSessionStore.getState().import).toMatchObject({ status: 'ready', file: { name: 'second.mp4' } });
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
});
