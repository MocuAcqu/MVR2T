import { createContext, useContext, type ReactNode } from 'react';
import { useAppInfo, type AppInfoState } from '@/hooks/useAppInfo';
import { useBackendHealth, type BackendHealthState } from '@/hooks/useBackendHealth';

interface SystemStatus {
  app: AppInfoState;
  backend: BackendHealthState;
  /** Electron 內可重新啟動後端；瀏覽器預覽為 null。 */
  restartBackend: (() => void) | null;
}

const SystemStatusContext = createContext<SystemStatus | null>(null);

/** Polls the backend once for the whole app (header and dashboard share the result). */
export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const app = useAppInfo();
  const { state: backend, restart } = useBackendHealth();
  return (
    <SystemStatusContext.Provider value={{ app, backend, restartBackend: restart }}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus(): SystemStatus {
  const value = useContext(SystemStatusContext);
  if (!value) throw new Error('useSystemStatus must be used inside <SystemStatusProvider>');
  return value;
}
