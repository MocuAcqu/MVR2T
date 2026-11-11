import { useState } from 'react';
import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { downloadAll } from '@/features/models/modelActions';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useUiStore } from '@/stores/uiStore';

/**
 * 首頁只在「有東西需要處理」時提醒；一切正常時不顯示，讓首頁保持乾淨。
 * - 後端沒啟動、缺 FFmpeg：警示
 * - 還沒下載 AI 模型（第一次使用）：提示卡片＋「全部下載」（使用者確認才下載，規格 §7.2）
 * - 下載中：顯示整體進度
 */
export function SystemNotice({ className }: { className?: string }) {
  const setPage = useUiStore((s) => s.setPage);
  const { backend, ffmpeg, models, applyModels } = useSystemStatus();
  const [error, setError] = useState<string | null>(null);

  const problems: string[] = [];
  if (backend.status === 'error') problems.push('本機後端沒有正常啟動。');
  if (ffmpeg.status === 'done' && !ffmpeg.ffmpeg.available) problems.push('還沒安裝 FFmpeg，無法處理影音檔。');

  const data = models.status === 'done' ? models.data : null;
  const downloading = data ? data.packages.filter((p) => p.job) : [];
  const missing = data ? data.packages.filter((p) => p.status !== 'installed' && !p.job) : [];
  const missingBytes = missing.reduce((s, p) => s + p.missing_bytes, 0);

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {problems.length > 0 ? (
        <div role="alert" className="flex flex-wrap items-center gap-4 rounded-xl bg-chip p-4">
          <Mono animation="error" scale={1} />
          <div className="min-w-0 flex-1 text-sm">
            {problems.map((p) => (
              <p key={p} className="font-medium">{p}</p>
            ))}
          </div>
          <Button size="sm" onClick={() => setPage('models')}>前往模型管理</Button>
        </div>
      ) : null}

      {downloading.length > 0 ? (
        <div role="status" className="flex flex-wrap items-center gap-4 rounded-xl bg-chip p-4">
          <Mono animation="loading" scale={1} />
          <div className="flex min-w-0 flex-1 flex-col gap-2 text-sm">
            {downloading.map((p) => (
              <div key={p.id} className="flex flex-col gap-1">
                <p className="font-medium">
                  {p.job?.status === 'queued' ? `${p.name}：排隊中` : `${p.name}：${p.job?.stage ?? ''}`}
                </p>
                <Progress label={`${p.name}下載進度`} value={p.job && p.job.total_bytes ? p.job.done_bytes / p.job.total_bytes : 0} />
              </div>
            ))}
          </div>
          <Button size="sm" variant="secondary" onClick={() => setPage('models')}>查看詳細</Button>
        </div>
      ) : missing.length > 0 ? (
        <div className="flex flex-wrap items-center gap-4 rounded-xl border-2 border-foreground p-4">
          <Mono animation="hint" scale={1} />
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-bold">還需要下載 AI 模型（約 {formatBytes(missingBytes)}）</p>
            <p className="text-body-gray">
              {missing.map((p) => p.name).join('、')}。只需下載一次，之後完全離線使用。
              {data ? `（剩餘空間 ${formatBytes(data.free_bytes)}）` : ''}
            </p>
            {error ? <p role="alert" className="mt-1 font-medium">{error}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => {
                setError(null);
                downloadAll()
                  .then(applyModels)
                  .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
              }}
            >
              全部下載
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPage('models')}>模型管理</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
