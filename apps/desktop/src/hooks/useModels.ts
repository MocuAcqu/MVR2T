import { useCallback, useEffect, useRef, useState } from 'react';
import type { ModelManagerState } from '@shared/types/api';
import { getBackendConnection, getModels } from '@/services/api';

export type ModelsState = { status: 'unknown' } | { status: 'loading' } | { status: 'done'; data: ModelManagerState };

/** 下載或驗證進行中時多久更新一次進度 */
const POLL_MS = 1000;

/**
 * 模型管理的狀態（GET /api/models，Phase 09）。下載或驗證進行中時每秒更新一次進度；完成後停止輪詢。
 * 動作（下載、取消…）的回應也是同一份狀態，用 apply() 立即更新畫面。
 */
export function useModels(backendKey: string | null): {
  state: ModelsState;
  refresh: () => void;
  apply: (data: ModelManagerState) => void;
} {
  const [state, setState] = useState<ModelsState>({ status: 'unknown' });
  const [nonce, setNonce] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!backendKey) {
      setState({ status: 'unknown' });
      return;
    }
    const controller = new AbortController();
    setState((s) => (s.status === 'done' ? s : { status: 'loading' }));
    const load = async () => {
      try {
        const conn = await getBackendConnection();
        if (!conn) return;
        const data = await getModels(conn, controller.signal);
        if (controller.signal.aborted) return;
        setState({ status: 'done', data });
        if (data.busy) timer.current = window.setTimeout(() => void load(), POLL_MS);
      } catch {
        if (!controller.signal.aborted) timer.current = window.setTimeout(() => void load(), POLL_MS * 3);
      }
    };
    void load();
    return () => {
      controller.abort();
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, [backendKey, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  const apply = useCallback(
    (data: ModelManagerState) => {
      setState({ status: 'done', data });
      if (data.busy) setNonce((n) => n + 1); // 開始輪詢
    },
    [],
  );
  return { state, refresh, apply };
}
