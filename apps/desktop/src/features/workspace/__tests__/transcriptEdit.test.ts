import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ getBackendConnection: vi.fn(), updateTranscript: vi.fn() }));
vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>();
  return { ...actual, ...api };
});

import type { TranscriptSegment } from '@shared/types/api';
import { segmentIndexAt } from '@/features/player/playerStore';
import { useSessionStore } from '@/stores/sessionStore';
import { deleteSegment, editText, mergeWithNext, saveSegments } from '../transcriptEdit';

const seg = (id: number, start: number, end: number, text: string, timing: 'aligned' | 'estimated' = 'aligned'): TranscriptSegment => ({
  id,
  start,
  end,
  text,
  timing,
  words: [{ text, start, end }],
});
const segments = [seg(0, 0, 2, '大家好'), seg(1, 2, 4, '今天開會'), seg(5, 4, 6, 'Thanks', 'estimated'), seg(6, 6, 8, 'everyone')];

describe('transcript editing', () => {
  it('editing text drops the word timings of that sentence only', () => {
    const out = editText(segments, 1, '今天要開會');
    expect(out[1]).toMatchObject({ id: 1, text: '今天要開會', words: [] });
    expect(out[0].words).toHaveLength(1);
    expect(editText(segments, 1, '今天開會')[1].words).toHaveLength(1); // unchanged text keeps words
  });

  it('deletes a sentence and keeps the other ids', () => {
    expect(deleteSegment(segments, 1).map((s) => s.id)).toEqual([0, 5, 6]);
  });

  it('merges with the next sentence: first id and start, second end; spaces only between words', () => {
    const zh = mergeWithNext(segments, 0);
    expect(zh[0]).toMatchObject({ id: 0, start: 0, end: 4, text: '大家好今天開會', timing: 'aligned' });
    expect(zh[0].words).toHaveLength(2);
    expect(zh.map((s) => s.id)).toEqual([0, 5, 6]);
    const en = mergeWithNext(segments, 5);
    expect(en[2]).toMatchObject({ id: 5, text: 'Thanks everyone', timing: 'estimated' });
    expect(mergeWithNext(segments, 6)).toBe(segments); // the last sentence has nothing to merge with
  });

  it('finds the sentence being played', () => {
    expect(segmentIndexAt(segments, 0)).toBe(0);
    expect(segmentIndexAt(segments, 3.5)).toBe(1);
    expect(segmentIndexAt(segments, 7.9)).toBe(3);
    expect(segmentIndexAt(segments, 20)).toBe(-1);
    expect(segmentIndexAt([], 1)).toBe(-1);
  });
});

describe('saveSegments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getBackendConnection.mockResolvedValue({ url: 'http://x', token: 't' });
  });

  it('stores the saved transcript and marks an existing summary as stale', async () => {
    const saved = { media_id: 'm1', segments: segments.slice(1), edited: true };
    api.updateTranscript.mockResolvedValue(saved);
    useSessionStore.setState({
      sessionId: 's1',
      import: { status: 'ready', file: { name: 'a.mp3', size: 1 }, info: { media_id: 'm1' } as never },
      summary: { media_id: 'm1' } as never,
      summaryStale: false,
    });
    await saveSegments(segments.slice(1));
    expect(api.updateTranscript).toHaveBeenCalledWith({ url: 'http://x', token: 't' }, 's1', 'm1', segments.slice(1));
    expect(useSessionStore.getState()).toMatchObject({ transcript: saved, summaryStale: true });
  });

  it('without a summary there is nothing to mark', async () => {
    api.updateTranscript.mockResolvedValue({ media_id: 'm1', segments: [] });
    useSessionStore.setState({ summary: null, summaryStale: false });
    await saveSegments([]);
    expect(useSessionStore.getState().summaryStale).toBe(false);
  });
});
