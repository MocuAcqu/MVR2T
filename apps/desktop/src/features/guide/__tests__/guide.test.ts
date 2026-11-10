import { describe, expect, it } from 'vitest';
import { nextGuideStep } from '../guide';

const base = {
  page: 'workspace' as const,
  importStatus: 'ready',
  extractionStatus: 'idle',
  transcriptionStatus: 'idle',
  summaryStatus: 'idle',
};

describe('nextGuideStep', () => {
  it('says nothing before a file is imported', () => {
    expect(nextGuideStep({ ...base, page: 'dashboard', importStatus: 'idle' })).toBeNull();
    expect(nextGuideStep({ ...base, importStatus: 'uploading' })).toBeNull();
  });
  it('walks through the workflow in order', () => {
    expect(nextGuideStep({ ...base, page: 'dashboard' })).toBe('open-workspace');
    expect(nextGuideStep(base)).toBe('extract');
    expect(nextGuideStep({ ...base, extractionStatus: 'completed' })).toBe('transcribe');
    const transcribed = { ...base, extractionStatus: 'completed', transcriptionStatus: 'completed' };
    expect(nextGuideStep(transcribed)).toBe('summarize');
    expect(nextGuideStep({ ...transcribed, summaryStatus: 'running' })).toBeNull();
    expect(nextGuideStep({ ...transcribed, summaryStatus: 'completed' })).toBe('done');
  });
  it('stays quiet while working, after failures and on other pages', () => {
    for (const s of ['starting', 'queued', 'running', 'failed', 'cancelled']) {
      expect(nextGuideStep({ ...base, extractionStatus: s })).toBeNull();
      expect(nextGuideStep({ ...base, extractionStatus: 'completed', transcriptionStatus: s })).toBeNull();
    }
    expect(nextGuideStep({ ...base, page: 'models' })).toBeNull();
  });
});
