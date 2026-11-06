import { useEffect, useState } from 'react';
import type { AppInfo } from '@shared/types/ipc';
import { getAppInfo } from '@/services/api';

export type AppInfoState =
  | { status: 'loading' }
  | { status: 'electron'; info: AppInfo }
  | { status: 'browser' };

/** 判斷目前是否在 Electron 內執行，並取得應用程式資訊。 */
export function useAppInfo(): AppInfoState {
  const [state, setState] = useState<AppInfoState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    void getAppInfo().then((info) => {
      if (cancelled) return;
      setState(info ? { status: 'electron', info } : { status: 'browser' });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
