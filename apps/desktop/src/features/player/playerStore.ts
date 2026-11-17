/**
 * 工作區播放器的狀態（規格 §2.1-D「依時間戳記定位原始影音」、§12.4「播放器」）。
 * 逐字稿與摘要只需要呼叫 seekTo()，不必知道播放器在哪裡。只在記憶體中。
 */
import { create } from 'zustand';

interface PlayerState {
  /** 目前播放位置（秒）；約每 0.25 秒更新 */
  time: number;
  playing: boolean;
  /** 播放器已載入可以播放的影音 */
  ready: boolean;
  set: (patch: Partial<Omit<PlayerState, 'set'>>) => void;
}

export const usePlayerStore = create<PlayerState>((set) => ({
  time: 0,
  playing: false,
  ready: false,
  set: (patch) => set(patch),
}));

let element: HTMLMediaElement | null = null;

export function registerPlayer(el: HTMLMediaElement | null): void {
  element = el;
  if (!el) usePlayerStore.getState().set({ time: 0, playing: false, ready: false });
}

/** 跳到某個時間；play = true 時從那裡開始播放。播放器還沒準備好時回傳 false。 */
export function seekTo(seconds: number, play = true): boolean {
  const el = element;
  if (!el || !usePlayerStore.getState().ready) return false;
  el.currentTime = Math.max(0, seconds);
  if (play) void el.play().catch(() => undefined);
  return true;
}

/** 目前時間落在哪一句（segments 依開始時間排序）；沒有則 -1。 */
export function segmentIndexAt(segments: readonly { start: number; end: number }[], time: number): number {
  let lo = 0;
  let hi = segments.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segments[mid].start <= time) {
      found = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (found >= 0 && time > segments[found].end + 0.5) return -1;
  return found;
}
