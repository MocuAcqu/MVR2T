import { describe, expect, it } from 'vitest';
import { idleExtraction, idleTranscription } from '@/stores/sessionStore';
import { isBusy, transcriptionNotification } from '../backgroundEffects';

const ready = { status: 'ready', file: {} as File, info: { filename: '會議.mp3' } } as never;
const t = (status: string, extra: object = {}) => ({ ...idleTranscription, status, ...extra }) as never;

describe('isBusy', () => {
  it('is busy while importing, extracting or transcribing', () => {
    const base = { import: ready, extraction: idleExtraction, transcription: idleTranscription };
    expect(isBusy(base)).toBe(false);
    expect(isBusy({ ...base, import: { status: 'uploading' } as never })).toBe(true);
    expect(isBusy({ ...base, extraction: { ...idleExtraction, status: 'running' } })).toBe(true);
    expect(isBusy({ ...base, transcription: t('queued') })).toBe(true);
    expect(isBusy({ ...base, transcription: t('completed') })).toBe(false);
  });
});

describe('transcriptionNotification', () => {
  const transcript = { segments: [{}, {}, {}] } as never;
  it('notifies when a running transcription completes', () => {
    const n = transcriptionNotification(
      { transcription: t('running') },
      { transcription: t('completed', { result: { audio_seconds: 90 } }), transcript, import: ready },
    );
    expect(n?.title).toBe('逐字稿完成');
    expect(n?.body).toContain('會議.mp3');
    expect(n?.body).toContain('3 句');
  });
  it('notifies on failure with the reason', () => {
    const n = transcriptionNotification(
      { transcription: t('running') },
      { transcription: t('failed', { message: '記憶體不足。' }), transcript: null, import: ready },
    );
    expect(n).toEqual({ title: '語音辨識失敗', body: '記憶體不足。' });
  });
  it('stays quiet for cancel, progress updates and when nothing was running', () => {
    expect(transcriptionNotification({ transcription: t('running') }, { transcription: t('cancelled'), transcript: null, import: ready })).toBeNull();
    expect(transcriptionNotification({ transcription: t('running') }, { transcription: t('running'), transcript: null, import: ready })).toBeNull();
    expect(transcriptionNotification({ transcription: t('completed') }, { transcription: t('completed'), transcript, import: ready })).toBeNull();
  });
});
