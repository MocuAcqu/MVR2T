import { useCallback, useEffect, useMemo, useState } from 'react';
import type { HealthResponse } from '@shared/types/api';
import type { BackendState } from '@shared/types/ipc';
import { browserFallbackConnection, fetchHealth, type BackendConnection } from '@/services/api';
import { t } from '@/i18n';

export type BackendHealthState =
  | { status: 'checking'; backendUrl: string | null }
  /** Electron 已啟動後端行程，等待就緒。 */
  | { status: 'starting'; backendUrl: null }
  | { status: 'online'; backendUrl: string; health: HealthResponse }
  | { status: 'offline'; backendUrl: string | null }
  /** Electron 無法啟動後端或後端意外結束。 */
  | { status: 'error'; backendUrl: null; message: string; logTail: string[] };

export interface BackendHealth {
  state: BackendHealthState;
  /** 只有在 Electron 內才能重新啟動後端。 */
  restart: (() => void) | null;
}

const RETRY_MS = 3000; // 離線時較頻繁重試
const HEARTBEAT_MS = 10000; // 上線後降低頻率

/** 以健康檢查輪詢某個後端連線。connection 為 null 時不輪詢。 */
function usePolling(connection: BackendConnection | null, enabled: boolean): BackendHealthState | null {
  const [state, setState] = useState<BackendHealthState | null>(null);

  useEffect(() => {
    if (!enabled || !connection) {
      setState(null);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setState({ status: 'checking', backendUrl: connection.url });

    const check = async () => {
      try {
        const health = await fetchHealth(connection, controller.signal);
        if (controller.signal.aborted) return;
        setState({ status: 'online', backendUrl: connection.url, health });
        timer = setTimeout(check, HEARTBEAT_MS);
      } catch {
        if (controller.signal.aborted) return;
        setState({ status: 'offline', backendUrl: connection.url });
        timer = setTimeout(check, RETRY_MS);
      }
    };
    void check();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [connection, enabled]);

  return state;
}

/** 訂閱 Electron Main 回報的後端行程狀態。 */
function useManagedBackendState(): BackendState | null {
  const [state, setState] = useState<BackendState | null>(null);
  useEffect(() => {
    const bridge = window.mvr2t;
    if (!bridge) return;
    let cancelled = false;
    const unsubscribe = bridge.onBackendState((s) => !cancelled && setState(s));
    void bridge.getBackendState().then((s) => !cancelled && setState(s)).catch(() => undefined);
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);
  return state;
}

/** 後端狀態：Electron 內以 Main 回報的行程狀態為主，瀏覽器預覽則直接輪詢預設位址。 */
export function useBackendHealth(): BackendHealth {
  const inElectron = !!window.mvr2t;
  const managed = useManagedBackendState();

  // 只在 url / token 改變時建立新的連線物件，避免每次 render 都重啟輪詢。
  const url = inElectron ? (managed?.phase === 'running' ? managed.url : null) : browserFallbackConnection().url;
  const token = inElectron ? (managed?.token ?? null) : null;
  const connection = useMemo<BackendConnection | null>(() => (url ? { url, token } : null), [url, token]);

  const polled = usePolling(connection, !!connection);
  const restart = useCallback(() => {
    void window.mvr2t?.restartBackend();
  }, []);

  if (!inElectron) {
    return { state: polled ?? { status: 'checking', backendUrl: null }, restart: null };
  }
  let state: BackendHealthState;
  switch (managed?.phase) {
    case undefined:
      state = { status: 'checking', backendUrl: null };
      break;
    case 'starting':
      state = { status: 'starting', backendUrl: null };
      break;
    case 'error':
      state = {
        status: 'error',
        backendUrl: null,
        message: managed.message ?? t('後端發生未知錯誤。'),
        logTail: managed.logTail,
      };
      break;
    case 'running':
      state = polled ?? { status: 'checking', backendUrl: managed.url };
      break;
    default: // stopping / stopped
      state = { status: 'offline', backendUrl: null };
  }
  return { state, restart };
}
