/** 設定頁（規格 §12.4）的介面偏好：存在 Main 的 preferences.json；一般瀏覽器預覽時只在記憶體中。 */
import { create } from 'zustand';
import type { UiPrefs } from '@shared/types/ipc';
import { defaultLang, setLang } from '@/i18n';

interface UiPrefsState extends UiPrefs {
  loaded: boolean;
}

export const useUiPrefs = create<UiPrefsState>(() => ({ asrLanguage: 'auto', language: 'zh-TW', loaded: false }));

const bridge = () => (typeof window !== 'undefined' ? window.mvr2t : undefined);

function apply(p: UiPrefs): void {
  useUiPrefs.setState({ asrLanguage: p.asrLanguage, language: p.language, loaded: true });
  setLang(p.language);
}

export async function loadUiPrefs(): Promise<void> {
  try {
    const b = bridge();
    const p = b ? await b.getUiPrefs() : null;
    if (p) apply(p);
    else apply({ asrLanguage: 'auto', language: defaultLang(typeof navigator !== 'undefined' ? navigator.language : undefined) });
  } catch {
    useUiPrefs.setState({ loaded: true });
  }
}

export async function setUiPrefs(patch: Partial<UiPrefs>): Promise<void> {
  const b = bridge();
  const { asrLanguage, language } = useUiPrefs.getState();
  apply(b ? await b.setUiPrefs(patch) : { asrLanguage, language, ...patch });
}
