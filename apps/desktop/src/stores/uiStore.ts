import { create } from 'zustand';

export type PageId = 'dashboard' | 'workspace' | 'models' | 'settings' | 'styleguide';

interface UiState {
  page: PageId;
  setPage: (page: PageId) => void;
}

/** In-app navigation. UI state only; nothing is persisted. */
export const useUiStore = create<UiState>((set) => ({
  page: 'dashboard',
  setPage: (page) => set({ page }),
}));
