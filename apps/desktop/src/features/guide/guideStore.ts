import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface GuideState {
  /**
   * 操作引導開關（設定頁）。開啟時每一步都會提示，沒有「知道了／不再提示」（使用者 2026-11-09 決定）。
   * 這是介面偏好，不含任何媒體資料（規格 §8.3 允許保存）。
   */
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
}

export const useGuideStore = create<GuideState>()(
  persist(
    (set) => ({
      enabled: true,
      setEnabled: (enabled) => set({ enabled }),
    }),
    {
      name: 'mvr2t-guide',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ enabled: s.enabled }),
    },
  ),
);
