import { describe, expect, it } from 'vitest';
import { isAppUrl, isSafeExternalUrl, parseNotification, parseSaveRequest, rendererOrigins } from './security';

const prod = { indexFileUrl: 'file:///C:/Users/User/Desktop/MVR2T%20AI/apps/desktop/dist/index.html' };
const dev = { devServerUrl: 'http://127.0.0.1:5173', indexFileUrl: prod.indexFileUrl };

describe('isAppUrl', () => {
  it('accepts the packaged index.html (path with spaces, any case, hash/query)', () => {
    expect(isAppUrl('file:///C:/Users/User/Desktop/MVR2T%20AI/apps/desktop/dist/index.html', prod)).toBe(true);
    expect(isAppUrl('file:///c:/users/user/desktop/mvr2t%20ai/apps/desktop/dist/index.html#x', prod)).toBe(true);
  });
  it('rejects other local files and remote pages in production', () => {
    expect(isAppUrl('file:///C:/Windows/System32/evil.html', prod)).toBe(false);
    expect(isAppUrl('https://example.com/', prod)).toBe(false);
    expect(isAppUrl('http://127.0.0.1:5173/', prod)).toBe(false);
    expect(isAppUrl('not a url', prod)).toBe(false);
  });
  it('accepts only the dev server origin in development', () => {
    expect(isAppUrl('http://127.0.0.1:5173/', dev)).toBe(true);
    expect(isAppUrl('http://127.0.0.1:5173/src/main.tsx', dev)).toBe(true);
    expect(isAppUrl('http://127.0.0.1:5174/', dev)).toBe(false);
    expect(isAppUrl('http://localhost:5173/', dev)).toBe(false);
    expect(isAppUrl(prod.indexFileUrl, dev)).toBe(false);
  });
});

describe('isSafeExternalUrl', () => {
  it('only allows https', () => {
    expect(isSafeExternalUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe(true);
    expect(isSafeExternalUrl('http://example.com')).toBe(false);
    expect(isSafeExternalUrl('file:///etc/passwd')).toBe(false);
    expect(isSafeExternalUrl('javascript:alert(1)')).toBe(false);
    expect(isSafeExternalUrl('nonsense')).toBe(false);
  });
});

describe('rendererOrigins', () => {
  it('maps to the CORS origin the backend must allow', () => {
    expect(rendererOrigins('http://127.0.0.1:5173')).toEqual(['http://127.0.0.1:5173']);
    expect(rendererOrigins(undefined)).toEqual(['null']);
  });
});

describe('parseNotification', () => {
  it('accepts a title and body', () => {
    expect(parseNotification({ title: '逐字稿完成', body: '共 320 句' })).toEqual({ title: '逐字稿完成', body: '共 320 句' });
  });
  it('rejects anything else from the renderer', () => {
    for (const bad of [null, 'x', 1, {}, { title: 1, body: '' }, { title: 'a' }, { title: '   ', body: 'b' }]) {
      expect(parseNotification(bad)).toBeNull();
    }
  });
  it('strips control characters and limits length', () => {
    const n = parseNotification({ title: 'a\nb' + 'x'.repeat(200), body: 'y'.repeat(500) });
    expect(n?.title).not.toMatch(/\n/);
    expect(n?.title.length).toBe(80);
    expect(n?.body.length).toBe(240);
  });
});

describe('parseSaveRequest', () => {
  const png = Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), Buffer.from('rest')]).toString('base64');
  it('accepts a PNG (base64) and an SVG (text)', () => {
    expect(parseSaveRequest({ defaultName: '心智圖', kind: 'png', data: png })?.fileName).toBe('心智圖.png');
    const svg = parseSaveRequest({ defaultName: 'map.svg', kind: 'svg', data: '<svg xmlns="http://www.w3.org/2000/svg"></svg>' });
    expect(svg?.fileName).toBe('map.svg');
  });
  it('strips folders and characters Windows does not allow from the name', () => {
    expect(parseSaveRequest({ defaultName: '..\\..\\Windows\\a:b?.png', kind: 'png', data: png })?.fileName).toBe('a_b_.png');
    expect(parseSaveRequest({ defaultName: '', kind: 'png', data: png })?.fileName).toBe('MVR2T.png');
  });
  it('rejects unknown kinds and content that is not what it claims to be', () => {
    expect(parseSaveRequest({ defaultName: 'x', kind: 'exe', data: png })).toBeNull();
    expect(parseSaveRequest({ defaultName: 'x', kind: 'png', data: Buffer.from('MZ').toString('base64') })).toBeNull();
    expect(parseSaveRequest({ defaultName: 'x', kind: 'svg', data: '<script>alert(1)</script>' })).toBeNull();
    expect(parseSaveRequest(null)).toBeNull();
  });
});
