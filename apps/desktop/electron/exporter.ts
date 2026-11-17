/**
 * 匯出面板（Phase 08）的 Main 端：驗證 renderer 傳來的請求、決定檔名、向後端取得檔案並寫入使用者選的資料夾。
 * 這個檔案不 import electron（PDF 列印以參數注入），方便單元測試。
 */
import { createWriteStream } from 'node:fs';
import { access, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { EXPORT_FORMATS, EXPORT_LABELS } from '@shared/constants/app';
import type { ExportContent, ExportFormat, ExportItem, ExportItemResult } from '@shared/types/ipc';
import { mt } from './i18n';

const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const SUMMARY_TYPES = ['overview', 'key_points', 'notes', 'topics', 'keywords', 'action_items', 'qa', 'mindmap'] as const;
const MAX_ITEMS = 40;
const MAX_PNG_BASE64 = 28_000_000; // 約 20 MB
const MAX_SVG_CHARS = 50 * 1024 * 1024;
const MAX_MINDMAP_JSON = 2 * 1024 * 1024;

export interface ParsedExport {
  sessionId: string;
  mediaId: string;
  baseName: string;
  items: ExportItem[];
  mindmap: unknown;
  mindmapPng: string | null;
  mindmapSvg: string | null;
  /** 只匯出這些摘要類型；null = 全部 */
  summaryTypes: string[] | null;
  /** 已設定固定資料夾時，這次仍要詢問 */
  askFolder: boolean;
  /** 重新匯出失敗的項目：用這次程式中最近一次匯出的資料夾，不再詢問 */
  useLastFolder: boolean;
}

/** 去掉路徑、Windows 不允許的字元與結尾的點／空白。 */
export function safeBaseName(name: string): string {
  const last = name.split(/[\\/]/).pop() ?? '';
  const stem = last.replace(/\.[A-Za-z0-9]{1,5}$/, '');
  // eslint-disable-next-line no-control-regex
  const clean = stem.replace(/[<>:"|?*\u0000-\u001f]/g, '_').replace(/^[.\s]+|[.\s]+$/g, '').slice(0, 100);
  return clean || 'MVR2T';
}

export function isSupported(content: string, format: string): content is ExportContent {
  return (
    Object.prototype.hasOwnProperty.call(EXPORT_FORMATS, content) &&
    (EXPORT_FORMATS[content as ExportContent] as readonly string[]).includes(format)
  );
}

/** IPC 傳入的內容不可信：只接受已知的內容與格式組合，檢查心智圖資料的格式與大小。 */
export function parseExportRequest(input: unknown): ParsedExport | null {
  if (!input || typeof input !== 'object') return null;
  const r = input as Record<string, unknown>;
  if (typeof r.sessionId !== 'string' || !ID_RE.test(r.sessionId)) return null;
  if (typeof r.mediaId !== 'string' || !ID_RE.test(r.mediaId)) return null;
  if (typeof r.baseName !== 'string' || !Array.isArray(r.items) || r.items.length === 0 || r.items.length > MAX_ITEMS) return null;
  const items: ExportItem[] = [];
  const seen = new Set<string>();
  for (const it of r.items) {
    if (!it || typeof it !== 'object') return null;
    const { content, format } = it as Record<string, unknown>;
    if (typeof content !== 'string' || typeof format !== 'string' || !isSupported(content, format)) return null;
    const key = `${content}/${format}`;
    if (!seen.has(key)) items.push({ content, format: format as ExportFormat });
    seen.add(key);
  }
  let mindmapPng: string | null = null;
  if (r.mindmapPng !== undefined && r.mindmapPng !== null) {
    if (typeof r.mindmapPng !== 'string' || r.mindmapPng.length > MAX_PNG_BASE64 || !/^[A-Za-z0-9+/]+={0,2}$/.test(r.mindmapPng)) return null;
    if (Buffer.from(r.mindmapPng.slice(0, 12), 'base64').subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') return null;
    mindmapPng = r.mindmapPng;
  }
  let mindmapSvg: string | null = null;
  if (r.mindmapSvg !== undefined && r.mindmapSvg !== null) {
    if (typeof r.mindmapSvg !== 'string' || r.mindmapSvg.length > MAX_SVG_CHARS || !/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/.test(r.mindmapSvg)) return null;
    mindmapSvg = r.mindmapSvg;
  }
  let summaryTypes: string[] | null = null;
  if (r.summaryTypes !== undefined && r.summaryTypes !== null) {
    if (!Array.isArray(r.summaryTypes) || r.summaryTypes.length > SUMMARY_TYPES.length) return null;
    if (!r.summaryTypes.every((t) => typeof t === 'string' && (SUMMARY_TYPES as readonly string[]).includes(t))) return null;
    summaryTypes = [...new Set(r.summaryTypes as string[])];
  }
  let mindmap: unknown = null;
  if (r.mindmap !== undefined && r.mindmap !== null) {
    if (typeof r.mindmap !== 'object' || JSON.stringify(r.mindmap).length > MAX_MINDMAP_JSON) return null;
    mindmap = r.mindmap;
  }
  return {
    sessionId: r.sessionId,
    mediaId: r.mediaId,
    baseName: safeBaseName(r.baseName),
    items,
    mindmap,
    mindmapPng,
    mindmapSvg,
    summaryTypes,
    askFolder: r.askFolder === true,
    useLastFolder: r.useLastFolder === true,
  };
}

export function fileNameFor(baseName: string, item: ExportItem): string {
  return `${baseName}-${EXPORT_LABELS[item.content]}.${item.format}`;
}

const exists = (p: string) =>
  access(p).then(
    () => true,
    () => false,
  );

/** 同名檔案已存在時加上「 (2)」「 (3)」…，不覆蓋使用者的檔案。 */
export async function uniquePath(folder: string, fileName: string, taken = new Set<string>()): Promise<string> {
  const ext = path.extname(fileName);
  const stem = fileName.slice(0, fileName.length - ext.length);
  for (let i = 1; i < 1000; i++) {
    const candidate = path.join(folder, i === 1 ? fileName : `${stem} (${i})${ext}`);
    if (!taken.has(candidate.toLowerCase()) && !(await exists(candidate))) {
      taken.add(candidate.toLowerCase());
      return candidate;
    }
  }
  throw new Error(mt('同名檔案太多'));
}

// ---------------------------------------------------------------------------
// Windows：防毒軟體（Defender 掃描新檔、Avast 勒索軟體防護…）可能短暫或持續阻擋改名
// 2026-11-11 使用者電腦：Avast 保護「文件」中的 Office 檔案，.partial → .docx 改名回傳 EPERM，直到使用者在 Avast 按「允許」。
// ---------------------------------------------------------------------------

const RETRY_CODES = new Set(['EPERM', 'EBUSY', 'EACCES']);
export const RENAME_RETRY_DELAYS = [50, 100, 200, 400, 800, 1500]; // 合計約 3 秒

const errCode = (err: unknown) => (err && typeof err === 'object' && 'code' in err ? String((err as { code: unknown }).code) : '');

/** 改名；遇到 EPERM／EBUSY／EACCES（檔案被暫時佔用或攔截）時等待後重試，其他錯誤直接丟出。 */
export async function renameWithRetry(
  from: string,
  to: string,
  delays: number[] = RENAME_RETRY_DELAYS,
  renameFn: (a: string, b: string) => Promise<void> = rename,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      await renameFn(from, to);
      return;
    } catch (err) {
      if (!RETRY_CODES.has(errCode(err)) || attempt >= delays.length) throw err;
      await sleep(delays[attempt]);
    }
  }
}

/** 給使用者看的錯誤訊息：權限錯誤多半是防毒軟體阻擋，說明怎麼處理。 */
export function friendlyError(err: unknown): string {
  const code = errCode(err);
  if (code === 'EPERM' || code === 'EACCES') {
    return mt('無法寫入檔案，可能被防毒軟體（例如勒索軟體防護）阻擋，或資料夾沒有寫入權限。請在防毒軟體中允許 MVR2T，再按「重新匯出失敗的項目」。');
  }
  if (code === 'EBUSY') return mt('檔案正被其他程式使用，請關閉後再按「重新匯出失敗的項目」。');
  if (code === 'ENOSPC') return mt('磁碟空間不足。');
  return err instanceof Error ? err.message : String(err);
}

export interface ExportDeps {
  backendUrl: string;
  token: string | null;
  /** 列印用 HTML → PDF（Electron 的隱藏視窗）；回傳 PDF bytes */
  printToPdf: (html: string) => Promise<Buffer>;
  fetchFn?: typeof fetch;
  /** 測試用：改名重試的等待時間 */
  renameRetryDelays?: number[];
}

async function backendError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
  } catch {
    // ignore
  }
  return mt('後端回應 {0}', res.status);
}

/** 依序匯出每個項目；單一項目失敗不影響其他項目。寫入時先寫 .partial，完成後才改名。 */
export async function runExport(req: ParsedExport, folder: string, deps: ExportDeps): Promise<ExportItemResult[]> {
  const fetchFn = deps.fetchFn ?? fetch;
  const taken = new Set<string>();
  const results: ExportItemResult[] = [];
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (deps.token) headers.Authorization = `Bearer ${deps.token}`;

  const fromBackend = async (item: ExportItem, format: string) => {
    const body: Record<string, unknown> = { session_id: req.sessionId, media_id: req.mediaId, content: item.content, format };
    if (item.content === 'summary') {
      if (req.mindmap) body.mindmap = req.mindmap;
      if (req.summaryTypes) body.summary_types = req.summaryTypes;
      if (req.mindmapPng && (format === 'docx' || format === 'html')) body.mindmap_png = req.mindmapPng;
    }
    const res = await fetchFn(`${deps.backendUrl}/api/export`, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok || !res.body) throw new Error(await backendError(res));
    return res;
  };

  for (const item of req.items) {
    let target: string | null = null;
    let partial: string | null = null;
    try {
      target = await uniquePath(folder, fileNameFor(req.baseName, item), taken);
      partial = `${target}.partial`;
      if (item.content === 'mindmap') {
        const data = item.format === 'png' ? (req.mindmapPng ? Buffer.from(req.mindmapPng, 'base64') : null) : req.mindmapSvg;
        if (!data) throw new Error(mt('還沒有心智圖。'));
        await writeFile(partial, data);
      } else if (item.format === 'pdf') {
        const res = await fromBackend(item, 'html');
        await writeFile(partial, await deps.printToPdf(await res.text()));
      } else {
        const res = await fromBackend(item, item.format);
        // 串流寫入：切段音檔 ZIP 可能數十 MB
        await pipeline(Readable.fromWeb(res.body as import('node:stream/web').ReadableStream), createWriteStream(partial));
      }
      await renameWithRetry(partial, target, deps.renameRetryDelays);
      results.push({ ...item, ok: true, path: target, error: null });
    } catch (err) {
      if (partial) await rm(partial, { force: true }).catch(() => undefined);
      results.push({ ...item, ok: false, path: null, error: friendlyError(err) });
    }
  }
  return results;
}

