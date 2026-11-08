import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useAppInfo, type AppInfoState } from '@/hooks/useAppInfo';
import { useBackendHealth, type BackendHealthState } from '@/hooks/useBackendHealth';
import { useFfmpegStatus, type FfmpegState } from '@/hooks/useFfmpegStatus';
import { useModels, type ModelsState } from '@/hooks/useModels';
import { ensureSession } from '@/features/media/mediaController';
import { getBackendConnection } from '@/services/api';

interface SystemStatus {
  app: AppInfoState;
  backend: BackendHealthState;
  /** Electron 內可重新啟動後端；瀏覽器預覽為 null。 */
  restartBackend: (() => void) | null;
  ffmpeg: FfmpegState;
  recheckFfmpeg: () => void;
  models: ModelsState;
  refreshModels: () => void;
}

const SystemStatusContext = createContext<SystemStatus | null>(null);

/** Polls the backend once for the whole app (header and dashboard share the result). */
export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const app = useAppInfo();
  const { state: backend, restart } = useBackendHealth();
  const onlineKey = backend.status === 'online' ? backend.backendUrl : null;
  const { state: ffmpeg, recheck } = useFfmpegStatus(onlineKey);
  const { state: models, refresh: refreshModels } = useModels(onlineKey);

  // 後端一上線就建立本次 Session。後端會同時刪除上一個 Session 的暫存
  // （例如使用者按了重新整理），符合「重新整理後資料清空」（規格 §8.3）。
  useEffect(() => {
    if (!onlineKey) return;
    void getBackendConnection()
      .then((conn) => (conn ? ensureSession(conn) : undefined))
      .catch(() => undefined);
  }, [onlineKey]);

  return (
    <SystemStatusContext.Provider value={{ app, backend, restartBackend: restart, ffmpeg, recheckFfmpeg: recheck, models, refreshModels }}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus(): SystemStatus {
  const value = useContext(SystemStatusContext);
  if (!value) throw new Error('useSystemStatus must be used inside <SystemStatusProvider>');
  return value;
}
