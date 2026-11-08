import { cn } from '@/lib/utils';

/**
 * 進度條：黑色填滿於 chip 灰色軌道上（設計規範：不使用彩色）。
 * value 為 0 ~ 1；indeterminate 時顯示來回移動的區塊（尚無法估算進度時使用）。
 */
export function Progress({
  value,
  indeterminate,
  label,
  className,
}: {
  value?: number;
  indeterminate?: boolean;
  /** 給螢幕閱讀器的名稱，例如「上傳進度」 */
  label: string;
  className?: string;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : pct}
      className={cn('relative h-2 w-full overflow-hidden rounded-pill bg-chip', className)}
    >
      {indeterminate ? (
        <div className="absolute inset-y-0 w-1/3 animate-indeterminate rounded-pill bg-foreground" />
      ) : (
        <div className="h-full rounded-pill bg-foreground transition-[width] duration-300" style={{ width: `${pct}%` }} />
      )}
    </div>
  );
}
