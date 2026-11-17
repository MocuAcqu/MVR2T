import type { BackendHealthState } from '@/hooks/useBackendHealth';
import { cn } from '@/lib/utils';
import { t } from '@/i18n';

export type DotState = 'ok' | 'fail' | 'pending';

/** Filled = ok, hollow = failed, dashed = checking. Always pair with text; never rely on shape alone. */
export function StatusDot({ state, className }: { state: DotState; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block size-2.5 shrink-0 rounded-full border-2 border-foreground',
        state === 'ok' && 'bg-foreground',
        state !== 'ok' && 'bg-background',
        state === 'pending' && 'border-dashed',
        className,
      )}
    />
  );
}

export function describeBackend(backend: BackendHealthState): { state: DotState; label: string } {
  if (backend.status === 'online') return { state: 'ok', label: t('後端已連線') };
  if (backend.status === 'checking') return { state: 'pending', label: t('正在檢查後端') };
  if (backend.status === 'starting') return { state: 'pending', label: t('後端啟動中') };
  if (backend.status === 'error') return { state: 'fail', label: t('後端發生錯誤') };
  return { state: 'fail', label: t('後端未連線') };
}
