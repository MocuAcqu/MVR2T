import { createContext, useContext, useEffect, type ReactNode } from 'react';
import type { ModelManagerState } from '@shared/types/api';
import { useAppInfo, type AppInfoState } from '@/hooks/useAppInfo';
import { useBackendHealth, type BackendHealthState } from '@/hooks/useBackendHealth';
import { useFfmpegStatus, type FfmpegState } from '@/hooks/useFfmpegStatus';
import { useModels, type ModelsState } from '@/hooks/useModels';
import { ensureSession } from '@/features/media/mediaController';
import { getBackendConnection } from '@/services/api';
import { useLang } from '@/i18n';

interface SystemStatus {
  app: AppInfoState;
  backend: BackendHealthState;
  /** Electron 內可重新啟動後端；瀏覽器預覽為 null。 */
  restartBackend: (() => void) | null;
  ffmpeg: FfmpegState;
  recheckFfmpeg: () => void;
  models: ModelsState;
  refreshModels: () => void;
  /** 套用模型管理動作的回應（下載、取消、刪除後的最新狀態） */
  applyModels: (data: ModelManagerState) => void;
}

const SystemStatusContext = createContext<SystemStatus | null>(null);

/** Polls the backend once for the whole app (header and dashboard share the result). */
export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const app = useAppInfo();
  const { state: backend, restart } = useBackendHealth();
  const onlineKey = backend.status === 'online' ? backend.backendUrl : null;
  // 後端回傳的訊息（模型名稱與說明、FFmpeg 狀態）依介面語言翻譯：語言改變時重新讀取。
  // 這個 Provider 在 <AppShell key={lang}> 之外，切換語言不會重新掛載；啟動時也可能在讀到語言偏好之前就先讀取。
  const lang = useLang((s) => s.lang);
  const langKey = onlineKey ? `${onlineKey}|${lang}` : null;
  const { state: ffmpeg, recheck } = useFfmpegStatus(langKey);
  const { state: models, refresh: refreshModels, apply: applyModels } = useModels(langKey);

  // 後端一上線就建立本次 Session。後端會同時刪除上一個 Session 的暫存
  // （例如使用者按了重新整理），符合「重新整理後資料清空」（規格 §8.3）。
  useEffect(() => {
    if (!onlineKey) return;
    void getBackendConnection()
      .then((conn) => (conn ? ensureSession(conn) : undefined))
      .catch(() => undefined);
  }, [onlineKey]);

  return (
    <SystemStatusContext.Provider value={{ app, backend, restartBackend: restart, ffmpeg, recheckFfmpeg: recheck, models, refreshModels, applyModels }}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus(): SystemStatus {
  const value = useContext(SystemStatusContext);
  if (!value) throw new Error('useSystemStatus must be used inside <SystemStatusProvider>');
  return value;
}
