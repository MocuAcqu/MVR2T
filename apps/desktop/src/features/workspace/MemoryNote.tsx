import { AlertCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getBackendConnection, getSystemInfo } from '@/services/api';

const REFRESH_MS = 30_000;

/**
 * 可用記憶體偏少時的提醒（2026-11-17 使用者建議：剛開機只剩 2–3 GB 可用，曾當機黑屏）。
 * 後端每次重新讀取可用記憶體，依語音辨識（約 3 GB）／摘要（約 3.3 GB）的需求給出提醒；沒有提醒時不顯示。
 * 只在工作開始前顯示（active = false），進行中不輪詢。
 */
export function MemoryNote({ kind, active }: { kind: 'asr' | 'llm'; active: boolean }) {
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (active) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const conn = await getBackendConnection();
        if (conn) {
          const info = await getSystemInfo(conn);
          if (alive) setWarnings(info[kind].warnings);
        }
      } catch {
        // 讀不到就不提醒
      }
      if (alive) timer = setTimeout(() => void tick(), REFRESH_MS);
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [kind, active]);

  if (active || warnings.length === 0) return null;
  return (
    <div role="status" className="flex items-start gap-2 rounded-lg border border-foreground px-4 py-3 text-sm">
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        {warnings.map((w) => (
          <p key={w}>{w}</p>
        ))}
      </div>
    </div>
  );
}
