import { useCallback, useEffect, useState } from 'react';
import type { ModelsResponse } from '@shared/types/api';
import { getBackendConnection, getModels } from '@/services/api';

export type ModelsState = { status: 'unknown' } | { status: 'loading' } | { status: 'done'; data: ModelsResponse };

/** 後端上線後取得模型清單與安裝狀態；可重新檢查（例如剛執行完下載腳本）。 */
export function useModels(backendKey: string | null): { state: ModelsState; refresh: () => void } {
  const [state, setState] = useState<ModelsState>({ status: 'unknown' });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!backendKey) {
      setState({ status: 'unknown' });
      return;
    }
    const controller = new AbortController();
    setState((s) => (s.status === 'done' ? s : { status: 'loading' }));
    void (async () => {
      try {
        const conn = await getBackendConnection();
        if (!conn) return;
        const data = await getModels(conn, controller.signal);
        if (!controller.signal.aborted) setState({ status: 'done', data });
      } catch {
        if (!controller.signal.aborted) setState({ status: 'unknown' });
      }
    })();
    return () => controller.abort();
  }, [backendKey, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { state, refresh };
}
