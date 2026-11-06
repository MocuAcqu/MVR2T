import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

// Unit tests for pure logic (no DOM). Kept separate from vite.config so the app build is unaffected.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../../shared', import.meta.url)),
    },
  },
  test: {
    include: ['src/**/*.test.ts', 'electron/**/*.test.ts'],
    environment: 'node',
  },
});
