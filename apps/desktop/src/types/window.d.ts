import type { Mvr2tBridge } from '@shared/types/ipc';

declare global {
  interface Window {
    /** 由 Electron preload 注入；在一般瀏覽器中為 undefined。 */
    mvr2t?: Mvr2tBridge;
  }
}

export {};
