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
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
