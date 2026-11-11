import { create } from 'zustand';
import type { ExportContent } from '@shared/types/ipc';

/** 匯出面板的開關。卡片上的「匯出」以 focus 打開（只預先勾選那張卡片的內容）；右上角的「匯出」不帶 focus。 */
interface ExportUiState {
  open: boolean;
  focus: ExportContent[] | null;
  openPanel: (focus?: ExportContent[]) => void;
  close: () => void;
}

export const useExportUi = create<ExportUiState>()((set) => ({
  open: false,
  focus: null,
  openPanel: (focus) => set({ open: true, focus: focus ?? null }),
  close: () => set({ open: false }),
}));
