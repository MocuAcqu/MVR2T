import { useCallback, useEffect, useState } from 'react';
import type { FfmpegStatus } from '@shared/types/api';
import { getBackendConnection, getFfmpegStatus } from '@/services/api';

export type FfmpegState = { status: 'unknown' } | { status: 'checking' } | { status: 'done'; ffmpeg: FfmpegStatus };

/** 後端上線後查詢 FFmpeg 是否可用；可手動重新檢查（例如使用者剛安裝完）。 */
export function useFfmpegStatus(backendKey: string | null): { state: FfmpegState; recheck: () => void } {
  const [state, setState] = useState<FfmpegState>({ status: 'unknown' });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!backendKey) {
      setState({ status: 'unknown' });
      return;
    }
    const controller = new AbortController();
    setState({ status: 'checking' });
    void (async () => {
      try {
        const conn = await getBackendConnection();
        if (!conn) return;
        const ffmpeg = await getFfmpegStatus(conn, controller.signal);
        if (!controller.signal.aborted) setState({ status: 'done', ffmpeg });
      } catch {
        if (!controller.signal.aborted) setState({ status: 'unknown' });
      }
    })();
    return () => controller.abort();
  }, [backendKey, nonce]);

  const recheck = useCallback(() => setNonce((n) => n + 1), []);
  return { state, recheck };
}
