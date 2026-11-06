/**
 * 視窗與 IPC 的來源檢查（PROJECT_SPEC §11）。純函式，方便測試。
 */

/**
 * 判斷 URL 是否屬於本程式自己的頁面。
 * - 開發：Vite dev server（同一個 origin）。
 * - 正式：打包後的 dist/index.html（file://，且必須是同一個檔案）。
 */
export function isAppUrl(url: string, opts: { devServerUrl?: string; indexFileUrl: string }): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (opts.devServerUrl) {
    return parsed.origin === new URL(opts.devServerUrl).origin;
  }
  if (parsed.protocol !== 'file:') return false;
  // 比較時忽略 query / hash；Windows 路徑大小寫不敏感。
  const normalize = (u: URL) => decodeURIComponent(u.pathname).toLowerCase();
  return normalize(parsed) === normalize(new URL(opts.indexFileUrl));
}

/** 只允許用系統瀏覽器開啟 https 連結（例如未來的 YouTube 功能）。 */
export function isSafeExternalUrl(url: string): boolean {
  try {
    return new URL(url).protocol === 'https:';
  } catch {
    return false;
  }
}

/** 後端 CORS 需要允許的來源：開發為 dev server origin；file:// 頁面送出的 Origin 是 "null"。 */
export function rendererOrigins(devServerUrl?: string): string[] {
  return devServerUrl ? [new URL(devServerUrl).origin] : ['null'];
}
