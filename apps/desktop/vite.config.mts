import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

/**
 * 正式版 Content-Security-Policy（PROJECT_SPEC §11）。
 * - 只載入本機打包的 script / style / 字型，不使用 CDN。
 * - connect-src 只允許本機後端（連接埠由作業系統動態分配，所以用 127.0.0.1:*）。
 * 開發模式（Vite HMR 需要 inline script / websocket）的 CSP 由 electron/main.ts 以標頭加入。
 */
const PROD_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "media-src 'self' blob:",
  'connect-src http://127.0.0.1:*',
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ');

function cspMeta(): Plugin {
  return {
    name: 'mvr2t-csp-meta',
    apply: 'build',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: PROD_CSP }, injectTo: 'head-prepend' },
    ],
  };
}

// base: './' 讓打包後的 index.html 可以用 file:// 載入（Electron 正式版）。
export default defineConfig({
  base: './',
  plugins: [react(), cspMeta()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../../shared', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    fs: { allow: ['../..'] }, // 允許讀取 repo 根目錄的 shared/
    // 開發模式的 HMR 在電腦睡眠、連線中斷後會「整頁重新載入」，記憶體中的工作階段會被清空（正式版沒有這個行為）。
    // 要在開發模式測試闔上筆電／睡眠時，先設定 MVR2T_DEV_NO_HMR=1 關閉 HMR（改程式後需手動按 Ctrl+R 重新整理）。
    ...(process.env.MVR2T_DEV_NO_HMR === '1' ? { hmr: false, ws: false as const } : {}),
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
