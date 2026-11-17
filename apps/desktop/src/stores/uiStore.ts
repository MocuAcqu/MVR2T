import { create } from 'zustand';

export type PageId = 'dashboard' | 'workspace' | 'models' | 'settings' | 'styleguide';

/** 切換頁面後要捲動到的區塊（例如用影片字幕匯入完成 → 工作區的逐字稿） */
export type FocusTarget = 'transcript';

interface UiState {
  page: PageId;
  focus: FocusTarget | null;
  setPage: (page: PageId) => void;
  /** 切換到某頁並捲動到指定區塊 */
  goTo: (page: PageId, focus: FocusTarget) => void;
  clearFocus: () => void;
}

/** In-app navigation. UI state only; nothing is persisted. */
export const useUiStore = create<UiState>((set) => ({
  page: 'dashboard',
  focus: null,
  setPage: (page) => set({ page, focus: null }),
  goTo: (page, focus) => set({ page, focus }),
  clearFocus: () => set({ focus: null }),
}));
