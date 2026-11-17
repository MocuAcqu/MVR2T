import { EXPORT_FORMATS, EXPORT_LABELS } from '@shared/constants/app';
import type { ExportContent, ExportFormat, ExportItem } from '@shared/types/ipc';
import { t } from '@/i18n';

/** 匯出面板（Phase 08）的內容列表與可用性。純函式，方便測試。 */
export const EXPORT_ROWS: { content: ExportContent; label: string; hint: string }[] = [
  { content: 'segments', label: EXPORT_LABELS.segments, hint: '每段的開始、結束、長度與切點' },
  { content: 'segments_audio', label: EXPORT_LABELS.segments_audio, hint: '每段的 WAV 音檔與切段清單，壓縮成一個 ZIP' },
  { content: 'transcript', label: EXPORT_LABELS.transcript, hint: '全文與時間戳記；SRT／VTT 是字幕檔' },
  { content: 'summary', label: EXPORT_LABELS.summary, hint: '已產生的摘要；Word 與 PDF 會附上目前的心智圖' },
  { content: 'mindmap', label: EXPORT_LABELS.mindmap, hint: '目前編輯後的心智圖' },
];

export const FORMAT_LABELS: Record<ExportFormat, string> = {
  txt: 'TXT',
  csv: 'CSV（Excel）',
  docx: 'Word',
  pdf: 'PDF',
  srt: 'SRT',
  vtt: 'VTT',
  json: 'JSON',
  md: 'Markdown',
  zip: 'ZIP',
  png: 'PNG',
  svg: 'SVG',
};

export interface Availability {
  segments: boolean;
  transcript: boolean;
  summary: boolean;
  mindmap: boolean;
}

export function unavailableReason(content: ExportContent, a: Availability): string | null {
  if ((content === 'segments' || content === 'segments_audio') && !a.segments) return t('請先完成「抽取音訊」');
  if (content === 'transcript' && !a.transcript) return t('請先完成「語音辨識」');
  if (content === 'summary' && !a.summary) return t('請先「產生摘要」');
  if (content === 'mindmap' && !a.mindmap) return t('請先產生心智圖');
  return null;
}

export type Selection = Partial<Record<ExportContent, ExportFormat[]>>;

/** 勾選 → 要匯出的項目（依表格順序；不可用的內容略過）。 */
export function selectedItems(sel: Selection, a: Availability): ExportItem[] {
  const items: ExportItem[] = [];
  for (const row of EXPORT_ROWS) {
    if (unavailableReason(row.content, a)) continue;
    const formats = EXPORT_FORMATS[row.content] as readonly ExportFormat[];
    for (const f of formats) if (sel[row.content]?.includes(f)) items.push({ content: row.content, format: f });
  }
  return items;
}

export function toggleFormat(sel: Selection, content: ExportContent, format: ExportFormat): Selection {
  const cur = sel[content] ?? [];
  return { ...sel, [content]: cur.includes(format) ? cur.filter((f) => f !== format) : [...cur, format] };
}

/** 需要心智圖圖片嗎：心智圖 PNG，或摘要的 Word／PDF（摘要包含心智圖時附圖）。 */
export function needsMindmapImage(items: ExportItem[], summaryIncludesMindmap = true): { png: boolean; svg: boolean } {
  const has = (c: ExportContent, f: ExportFormat) => items.some((i) => i.content === c && i.format === f);
  const forSummary = summaryIncludesMindmap && (has('summary', 'docx') || has('summary', 'pdf'));
  return { png: has('mindmap', 'png') || forSummary, svg: has('mindmap', 'svg') };
}

/** 切段音檔 ZIP 的估計大小（16 kHz、16-bit、單聲道 = 每秒 32 KB；切段重疊約多 3%）。 */
export const estimateZipBytes = (durationSeconds: number) => Math.round(durationSeconds * 32_000 * 1.03);

export const DEFAULT_SELECTION: Selection = { transcript: ['txt', 'srt'], summary: ['docx'] };

/** 從卡片的「匯出」打開時，每種內容預設勾選的格式（之前勾過就用之前的）。 */
export const CARD_DEFAULTS: Record<ExportContent, ExportFormat[]> = {
  segments: ['csv'],
  segments_audio: ['zip'],
  transcript: ['txt', 'srt'],
  summary: ['docx'],
  mindmap: ['png'],
};

/** 從卡片打開：只勾選那張卡片的內容。 */
export function presetSelection(focus: ExportContent[], remembered: Selection): Selection {
  const sel: Selection = {};
  for (const c of focus) sel[c] = remembered[c]?.length ? [...remembered[c]!] : [...CARD_DEFAULTS[c]];
  return sel;
}
