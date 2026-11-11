import { mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fileNameFor, friendlyError, parseExportRequest, renameWithRetry, runExport, safeBaseName, uniquePath } from './exporter';

const PNG_B64 = Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), Buffer.alloc(16)]).toString('base64');
const base = { sessionId: 'abc123', mediaId: 'm_1', baseName: '會議.m4a', items: [{ content: 'transcript', format: 'srt' }] };

describe('parseExportRequest', () => {
  it('accepts known content/format pairs and removes duplicates', () => {
    const r = parseExportRequest({ ...base, items: [...base.items, { content: 'transcript', format: 'srt' }, { content: 'summary', format: 'pdf' }] });
    expect(r?.items).toEqual([
      { content: 'transcript', format: 'srt' },
      { content: 'summary', format: 'pdf' },
    ]);
    expect(r?.baseName).toBe('會議');
  });

  it('rejects unknown pairs, bad ids and malformed mind map data', () => {
    expect(parseExportRequest({ ...base, items: [{ content: 'segments', format: 'srt' }] })).toBeNull();
    expect(parseExportRequest({ ...base, items: [{ content: 'transcript', format: 'exe' }] })).toBeNull();
    expect(parseExportRequest({ ...base, items: [] })).toBeNull();
    expect(parseExportRequest({ ...base, sessionId: '../x' })).toBeNull();
    expect(parseExportRequest({ ...base, mindmapPng: Buffer.from('GIF89a........').toString('base64') })).toBeNull();
    expect(parseExportRequest({ ...base, mindmapSvg: '<html>' })).toBeNull();
    expect(parseExportRequest({ ...base, mindmap: 'tree' })).toBeNull();
    expect(parseExportRequest({ ...base, mindmapPng: PNG_B64, mindmapSvg: '<svg xmlns="x"></svg>', mindmap: { id: 'n' } })).not.toBeNull();
  });

  it('makes file names safe on Windows', () => {
    expect(safeBaseName('C:\\x\\a<b>:c?.mp4')).toBe('a_b__c_');
    expect(safeBaseName('...')).toBe('MVR2T');
    expect(fileNameFor('會議', { content: 'segments_audio', format: 'zip' })).toBe('會議-切段音檔.zip');
  });
});

describe('runExport', () => {
  let dir: string;
  beforeEach(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'mvr2t-export-'));
  });
  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  it('never overwrites: adds (2), (3)', async () => {
    await writeFile(path.join(dir, 'a-逐字稿.txt'), 'old');
    const taken = new Set<string>();
    expect(path.basename(await uniquePath(dir, 'a-逐字稿.txt', taken))).toBe('a-逐字稿 (2).txt');
    expect(path.basename(await uniquePath(dir, 'a-逐字稿.txt', taken))).toBe('a-逐字稿 (3).txt');
  });

  it('writes backend files, prints PDFs, writes mind map images; one failure does not stop the rest', async () => {
    const calls: Record<string, unknown>[] = [];
    const fetchFn = (async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      calls.push({ ...body, auth: (init.headers as Record<string, string>).Authorization });
      if (body.content === 'segments') return new Response(JSON.stringify({ detail: '還沒有抽取音訊與切段' }), { status: 404 });
      return new Response(body.format === 'html' ? '<html>print</html>' : `data:${body.content}.${body.format}`);
    }) as unknown as typeof fetch;
    const req = parseExportRequest({
      ...base,
      items: [
        { content: 'transcript', format: 'srt' },
        { content: 'segments', format: 'csv' },
        { content: 'summary', format: 'pdf' },
        { content: 'summary', format: 'md' },
        { content: 'mindmap', format: 'png' },
        { content: 'mindmap', format: 'svg' },
      ],
      mindmap: { id: 'n', text: '中心' },
      mindmapPng: PNG_B64,
    })!;
    const printed: string[] = [];
    const results = await runExport(req, dir, {
      backendUrl: 'http://127.0.0.1:1',
      token: 'tok',
      fetchFn,
      printToPdf: async (html) => {
        printed.push(html);
        return Buffer.from('%PDF-1.7');
      },
    });
    expect(results.map((r) => r.ok)).toEqual([true, false, true, true, true, false]);
    expect(results[1].error).toContain('抽取音訊');
    expect(results[5].error).toContain('心智圖');
    expect(printed).toEqual(['<html>print</html>']);
    expect(await readFile(path.join(dir, '會議-逐字稿.srt'), 'utf8')).toBe('data:transcript.srt');
    expect(await readFile(path.join(dir, '會議-摘要.pdf'), 'utf8')).toBe('%PDF-1.7');
    expect((await readFile(path.join(dir, '會議-心智圖.png'))).toString('base64')).toBe(PNG_B64);
    // summary requests carry the edited mind map; the picture only goes to DOCX / PDF (html)
    const summaryCalls = calls.filter((c) => c.content === 'summary');
    expect(summaryCalls.every((c) => (c.mindmap as { text: string }).text === '中心')).toBe(true);
    expect(summaryCalls.find((c) => c.format === 'html')?.mindmap_png).toBe(PNG_B64);
    expect(summaryCalls.find((c) => c.format === 'md')?.mindmap_png).toBeUndefined();
    expect(calls.every((c) => c.auth === 'Bearer tok')).toBe(true);
    expect((await readdir(dir)).some((f) => f.endsWith('.partial'))).toBe(false); // failed items leave nothing behind
  });
});

describe('renameWithRetry (Windows antivirus / file locks)', () => {
  const fail = (code: string) => Object.assign(new Error(`${code}: operation not permitted, rename`), { code });

  it('retries EPERM / EBUSY / EACCES and then succeeds', async () => {
    const codes = ['EPERM', 'EBUSY', 'EACCES'];
    const waits: number[] = [];
    let calls = 0;
    await renameWithRetry('a', 'b', [1, 2, 3, 4], async () => {
      if (calls < codes.length) throw fail(codes[calls++]);
      calls++;
    }, async (ms) => void waits.push(ms));
    expect(calls).toBe(4);
    expect(waits).toEqual([1, 2, 3]);
  });

  it('gives up after the last delay with the original error, and never retries other errors', async () => {
    let calls = 0;
    await expect(renameWithRetry('a', 'b', [1, 1], async () => { calls++; throw fail('EPERM'); }, async () => undefined)).rejects.toMatchObject({ code: 'EPERM' });
    expect(calls).toBe(3);
    calls = 0;
    await expect(renameWithRetry('a', 'b', [1, 1], async () => { calls++; throw fail('ENOENT'); }, async () => undefined)).rejects.toMatchObject({ code: 'ENOENT' });
    expect(calls).toBe(1);
  });

  it('explains permission errors in plain words', () => {
    expect(friendlyError(fail('EPERM'))).toContain('防毒軟體');
    expect(friendlyError(fail('EACCES'))).toContain('允許 MVR2T');
    expect(friendlyError(new Error('還沒有心智圖。'))).toBe('還沒有心智圖。');
  });
});
