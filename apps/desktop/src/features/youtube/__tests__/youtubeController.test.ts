import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  createSession: vi.fn(),
  getBackendConnection: vi.fn(),
  getTask: vi.fn(),
  cancelTask: vi.fn(),
  getTranscript: vi.fn(),
  getYtDlp: vi.fn(),
  probeYouTube: vi.fn(),
  startYouTubeDownload: vi.fn(),
  uploadMedia: vi.fn(),
}));

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ...actual, ...api };
});

import { ApiError } from '@/services/api';
import { __resetForTests, importFile, startExtraction } from '@/features/media/mediaController';
import { idleExtraction, idleSummary, idleTranscription, useSessionStore } from '@/stores/sessionStore';
import {
  __resetYouTubeForTests,
  acceptYouTubeNotice,
  downloadVideo,
  loadYouTubeStatus,
  probeVideo,
  setYouTubeUrl,
  useYouTubeStore,
} from '../youtubeController';

const conn = { url: 'http://127.0.0.1:5000', token: 'a' };
const video = {
  video_id: 'jNQXAC9IVRw',
  url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
  title: 'Me at the zoo',
  channel: 'jawed',
  duration: 19,
  audio_size: 300000,
  subtitles: [{ lang: 'en', name: 'English' }],
};
const media = { media_id: 'm2', filename: 'Me at the zoo.m4a', size: 300000, duration: 19, origin: 'youtube' } as never;
const transcript = {
  media_id: 'm2',
  source: 'subtitles',
  language: 'English',
  timing: 'aligned',
  duration: 19,
  models: {},
  warnings: ['字幕'],
  segments: [{ id: 0, start: 0, end: 2, text: 'hi', timing: 'aligned', words: [] }],
} as never;

const flush = async () => {
  for (let i = 0; i < 10; i++) await Promise.resolve();
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  __resetForTests();
  __resetYouTubeForTests();
  useSessionStore.setState({
    sessionId: null,
    backendKey: null,
    import: { status: 'idle' },
    extraction: idleExtraction,
    transcription: idleTranscription,
    transcript: null,
    summarizing: idleSummary,
    summary: null,
    mindmap: null,
  });
  api.getBackendConnection.mockResolvedValue(conn);
  api.createSession.mockResolvedValue({ session_id: 's1' });
});

describe('YouTube notice and component status', () => {
  it('asks for the notice once (in-memory in the browser preview) and reads the component state', async () => {
    api.getYtDlp.mockResolvedValue({ installed: false, supported: true });
    await loadYouTubeStatus();
    expect(useYouTubeStore.getState().noticeAccepted).toBe(false);
    expect(useYouTubeStore.getState().component).toMatchObject({ installed: false });
    await acceptYouTubeNotice();
    await loadYouTubeStatus();
    expect(useYouTubeStore.getState().noticeAccepted).toBe(true);
  });
});

describe('probeVideo', () => {
  it('rejects non-video URLs without calling the backend', async () => {
    setYouTubeUrl('https://www.youtube.com/playlist?list=PL1');
    await probeVideo();
    expect(useYouTubeStore.getState()).toMatchObject({ phase: 'error' });
    expect(useYouTubeStore.getState().message).toContain('播放清單');
    expect(api.probeYouTube).not.toHaveBeenCalled();
  });

  it('loads the video information', async () => {
    api.probeYouTube.mockResolvedValue(video);
    setYouTubeUrl('youtu.be/jNQXAC9IVRw');
    await probeVideo();
    expect(api.probeYouTube).toHaveBeenCalledWith(conn, 's1', 'youtu.be/jNQXAC9IVRw', expect.any(AbortSignal));
    expect(useYouTubeStore.getState()).toMatchObject({ phase: 'ready', video });
  });

  it('shows the backend message (e.g. the component is missing)', async () => {
    api.probeYouTube.mockRejectedValue(new ApiError(412, '尚未下載 YouTube 下載元件。'));
    setYouTubeUrl('youtu.be/jNQXAC9IVRw');
    await probeVideo();
    expect(useYouTubeStore.getState()).toMatchObject({ phase: 'error', message: '尚未下載 YouTube 下載元件。' });
  });
});

describe('downloadVideo', () => {
  beforeEach(async () => {
    api.probeYouTube.mockResolvedValue(video);
    setYouTubeUrl('youtu.be/jNQXAC9IVRw');
    await probeVideo();
    api.startYouTubeDownload.mockResolvedValue({ task_id: 't1' });
  });

  it('with the uploaded subtitles: the media is ready and the transcript is already done', async () => {
    useSessionStore.setState({ import: { status: 'ready', file: { name: 'old.mp4', size: 1 }, info: { media_id: 'm1' } as never } });
    api.getTask.mockResolvedValue({ status: 'completed', progress: 1, result: { media, subtitles: true, warnings: [] } });
    api.getTranscript.mockResolvedValue(transcript);
    await downloadVideo(video.subtitles[0]);
    await flush();
    expect(api.startYouTubeDownload).toHaveBeenCalledWith(conn, 's1', video, video.subtitles[0]);
    const s = useSessionStore.getState();
    expect(s.import).toMatchObject({ status: 'ready', file: { name: 'Me at the zoo.m4a', size: 300000 }, info: media });
    expect(s.transcript).toBe(transcript);
    expect(s.transcription).toMatchObject({ status: 'completed', result: { segment_count: 1, audio_seconds: 19 } });
    expect(useYouTubeStore.getState()).toMatchObject({ phase: 'idle', url: '', video: null });

    // extracting audio afterwards keeps the subtitle transcript
    api.getTask.mockReset();
    api.getTask.mockResolvedValue({ status: 'running', progress: 0 });
    await startExtraction();
    expect(useSessionStore.getState().transcript).toBe(transcript);
  });

  it('without subtitles: only the media is ready (transcription still to do)', async () => {
    api.getTask.mockResolvedValue({ status: 'completed', progress: 1, result: { media, subtitles: false, warnings: [] } });
    await downloadVideo(null);
    await flush();
    expect(useSessionStore.getState().import).toMatchObject({ status: 'ready' });
    expect(useSessionStore.getState().transcript).toBeNull();
    expect(useSessionStore.getState().transcription.status).toBe('idle');
    expect(api.getTranscript).not.toHaveBeenCalled();
  });

  it('a failed download keeps the video so the user can retry', async () => {
    api.getTask.mockResolvedValue({ status: 'failed', progress: 0.2, message: '這是私人影片，無法下載。' });
    await downloadVideo(null);
    await flush();
    expect(useYouTubeStore.getState()).toMatchObject({ phase: 'ready', video, message: '這是私人影片，無法下載。' });
    expect(useSessionStore.getState().import.status).toBe('idle');
  });

  it('importing a local file cancels the YouTube download', async () => {
    api.getTask.mockResolvedValue({ status: 'running', progress: 0.3, stage: '正在下載音訊', detail: '' });
    api.cancelTask.mockResolvedValue({});
    api.uploadMedia.mockResolvedValue({ media_id: 'm9' });
    await downloadVideo(null);
    await flush();
    expect(useYouTubeStore.getState().phase).toBe('downloading');
    useSessionStore.setState({ sessionId: 's1' });
    await importFile({ name: 'b.mp3', size: 10 } as File);
    await flush();
    expect(api.cancelTask).toHaveBeenCalledWith(conn, 's1', 't1');
  });
});
