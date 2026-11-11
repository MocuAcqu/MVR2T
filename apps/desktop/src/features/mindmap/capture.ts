import type { SaveFileKind } from '@shared/types/ipc';

/**
 * 匯出面板需要心智圖的圖片，但圖片只能從畫面上的 React Flow 產生。
 * 心智圖編輯器顯示時在這裡登記「產生圖片」的函式；匯出面板呼叫 captureMindmap()。
 */
type Capture = (kind: SaveFileKind) => Promise<string>;
let current: Capture | null = null;

export function registerMindmapCapture(fn: Capture): () => void {
  current = fn;
  return () => {
    if (current === fn) current = null;
  };
}

/** 回傳 data URL；心智圖沒有顯示時回傳 null。 */
export async function captureMindmap(kind: SaveFileKind): Promise<string | null> {
  return current ? current(kind) : null;
}
