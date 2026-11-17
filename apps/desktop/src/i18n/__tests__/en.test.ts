import { afterEach, describe, expect, it } from 'vitest';
import { EN } from '../en';
import { defaultLang, setLang, t } from '../index';

/** 所有 renderer 原始碼（文字內容） */
const SOURCES = import.meta.glob<string>(['../../**/*.{ts,tsx}', '!../../**/__tests__/**', '!../../**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

afterEach(() => setLang('zh-TW'));

describe('English interface', () => {
  it('every t() text in the renderer has an English translation', () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(50);
    const missing = new Set<string>();
    for (const [f, text] of Object.entries(SOURCES)) {
      if (/StyleGuidePage|i18n\//.test(f)) continue;
      for (const m of text.matchAll(/\bt\('((?:[^'\\]|\\.)*)'/g)) {
        const key = m[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\');
        if (/[一-鿿　-〿！-～]/.test(key) && !(key in EN)) missing.add(`${f}: ${key}`);
      }
    }
    expect([...missing]).toEqual([]);
  });

  it('keeps the same placeholders', () => {
    const bad = Object.entries(EN).filter(([zh, en]) => (zh.match(/\{\d\}/g) ?? []).sort().join() !== (en.match(/\{\d\}/g) ?? []).sort().join());
    expect(bad).toEqual([]);
  });

  it('translates with arguments and falls back to the original text', () => {
    expect(t('匯出 {0} 個檔案', 3)).toBe('匯出 3 個檔案');
    setLang('en');
    expect(t('匯出 {0} 個檔案', 3)).toBe('Export 3 files');
    expect(t('沒有翻譯的句子')).toBe('沒有翻譯的句子');
  });

  it('first run follows the system language', () => {
    expect(defaultLang('zh-TW')).toBe('zh-TW');
    expect(defaultLang('zh-CN')).toBe('zh-TW');
    expect(defaultLang('en-US')).toBe('en');
    expect(defaultLang(undefined)).toBe('en');
  });
});
