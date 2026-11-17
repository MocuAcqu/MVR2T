/** 設定頁（規格 §12.4）的介面偏好：存在 Main 的 preferences.json；一般瀏覽器預覽時只在記憶體中。 */
import { create } from 'zustand';
import type { UiPrefs } from '@shared/types/ipc';

interface UiPrefsState extends UiPrefs {
  loaded: boolean;
}

export const useUiPrefs = create<UiPrefsState>(() => ({ asrLanguage: 'auto', loaded: false }));

const bridge = () => (typeof window !== 'undefined' ? window.mvr2t : undefined);

export async function loadUiPrefs(): Promise<void> {
  try {
    const b = bridge();
    const p = b ? await b.getUiPrefs() : null;
    useUiPrefs.setState({ ...(p ?? {}), loaded: true });
  } catch {
    useUiPrefs.setState({ loaded: true });
  }
}

export async function setUiPrefs(patch: Partial<UiPrefs>): Promise<void> {
  const b = bridge();
  const next = b ? await b.setUiPrefs(patch) : { ...useUiPrefs.getState(), ...patch };
  useUiPrefs.setState({ asrLanguage: next.asrLanguage });
}
