/**
 * 多語介面（使用者決定 2026-11-17：繁中／英文）。
 * 原文（繁體中文）就是 key：t('匯入影音') 在英文時查 EN 表，查不到就顯示原文。{0}、{1}… 代入參數。
 * 切換語言時 App 會重新繪製整個畫面（工作階段的資料在 store 中，不受影響）。
 */
import { create } from 'zustand';
import { EN } from './en';

export type Lang = 'zh-TW' | 'en';

export const useLang = create<{ lang: Lang }>(() => ({ lang: 'zh-TW' }));

export const getLang = (): Lang => useLang.getState().lang;

export function setLang(lang: Lang): void {
  useLang.setState({ lang });
  if (typeof document !== 'undefined') document.documentElement.lang = lang === 'en' ? 'en' : 'zh-Hant-TW';
}

/** 第一次使用（還沒選過）：依系統語言，中文系統用繁中，其他用英文。 */
export function defaultLang(locale: string | undefined): Lang {
  return locale && /^zh/i.test(locale) ? 'zh-TW' : 'en';
}

export function t(zh: string, ...args: (string | number | null | undefined)[]): string {
  const s = getLang() === 'en' ? (EN[zh] ?? zh) : zh;
  return args.length ? s.replace(/\{(\d+)\}/g, (_m, i: string) => String(args[Number(i)] ?? '')) : s;
}
