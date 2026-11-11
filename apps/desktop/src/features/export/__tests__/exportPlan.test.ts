import { describe, expect, it } from 'vitest';
import { EXPORT_FORMATS } from '@shared/constants/app';
import { EXPORT_ROWS, needsMindmapImage, presetSelection, selectedItems, toggleFormat, unavailableReason, type Availability } from '../exportPlan';

const all: Availability = { segments: true, transcript: true, summary: true, mindmap: true };

describe('export plan', () => {
  it('lists every exportable content, in the workflow order', () => {
    expect(EXPORT_ROWS.map((r) => r.content)).toEqual(Object.keys(EXPORT_FORMATS));
  });

  it('skips content that does not exist yet and explains why', () => {
    const none: Availability = { segments: false, transcript: false, summary: false, mindmap: false };
    expect(unavailableReason('segments_audio', none)).toContain('抽取音訊');
    expect(unavailableReason('transcript', none)).toContain('語音辨識');
    expect(unavailableReason('transcript', all)).toBeNull();
    const sel = { transcript: ['srt' as const], summary: ['pdf' as const] };
    expect(selectedItems(sel, { ...all, summary: false })).toEqual([{ content: 'transcript', format: 'srt' }]);
  });

  it('keeps the table order and toggles formats', () => {
    let sel = toggleFormat({}, 'summary', 'md');
    sel = toggleFormat(sel, 'transcript', 'csv');
    sel = toggleFormat(sel, 'transcript', 'txt');
    expect(selectedItems(sel, all)).toEqual([
      { content: 'transcript', format: 'txt' },
      { content: 'transcript', format: 'csv' },
      { content: 'summary', format: 'md' },
    ]);
    expect(selectedItems(toggleFormat(sel, 'summary', 'md'), all)).toHaveLength(2);
  });

  it('captures the mind map picture only when needed', () => {
    expect(needsMindmapImage([{ content: 'summary', format: 'md' }])).toEqual({ png: false, svg: false });
    expect(needsMindmapImage([{ content: 'summary', format: 'pdf' }])).toEqual({ png: true, svg: false });
    expect(needsMindmapImage([{ content: 'mindmap', format: 'svg' }])).toEqual({ png: false, svg: true });
  });

  it('does not capture the picture for a summary without the mind map', () => {
    expect(needsMindmapImage([{ content: 'summary', format: 'docx' }], false)).toEqual({ png: false, svg: false });
  });

  it('opening from a card pre-selects only that card (remembered formats first)', () => {
    expect(presetSelection(['segments', 'segments_audio'], {})).toEqual({ segments: ['csv'], segments_audio: ['zip'] });
    expect(presetSelection(['transcript'], { transcript: ['vtt'], summary: ['md'] })).toEqual({ transcript: ['vtt'] });
  });
});
