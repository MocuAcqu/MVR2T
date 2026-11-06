import { describe, expect, it } from 'vitest';
import { isAppUrl, isSafeExternalUrl, rendererOrigins } from './security';

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
