import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { useSessionStore } from '@/stores/sessionStore';
import type { GuideStepId } from './guide';

interface GuideState {
  /** 「不再提示」會關閉；可在設定頁重新開啟。這是介面偏好，不含任何媒體資料（規格 §8.3 允許保存）。 */
  enabled: boolean;
  /** 這個檔案已按「知道了」的步驟。只在記憶體中，換檔案時清空。 */
  dismissed: GuideStepId[];
  setEnabled: (enabled: boolean) => void;
  dismiss: (step: GuideStepId) => void;
  resetDismissed: () => void;
}

export const useGuideStore = create<GuideState>()(
  persist(
    (set) => ({
      enabled: true,
      dismissed: [],
      setEnabled: (enabled) => set({ enabled, dismissed: [] }),
      dismiss: (step) => set((s) => ({ dismissed: s.dismissed.includes(step) ? s.dismissed : [...s.dismissed, step] })),
      resetDismissed: () => set({ dismissed: [] }),
    }),
    {
      name: 'mvr2t-guide',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ enabled: s.enabled }), // 只保存開關
    },
  ),
);

// 「知道了」只對目前這個檔案有效：檔案移除或更換（匯入狀態回到 idle / 重新上傳）時清空。
useSessionStore.subscribe((s, prev) => {
  if (s.import.status !== prev.import.status && (s.import.status === 'idle' || s.import.status === 'uploading')) {
    useGuideStore.getState().resetDismissed();
  }
});
