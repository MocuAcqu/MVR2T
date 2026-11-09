import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { cn } from '@/lib/utils';
import { useUiStore } from '@/stores/uiStore';

/**
 * 首頁只在「有東西需要處理」時提醒（後端沒啟動、缺 FFmpeg、缺語音辨識模型）；
 * 詳細狀態在「模型管理」頁。一切正常時不顯示，讓首頁保持乾淨。
 */
export function SystemNotice({ className }: { className?: string }) {
  const setPage = useUiStore((s) => s.setPage);
  const { backend, ffmpeg, models } = useSystemStatus();

  const problems: string[] = [];
  if (backend.status === 'error') problems.push('本機後端沒有正常啟動。');
  if (ffmpeg.status === 'done' && !ffmpeg.ffmpeg.available) problems.push('還沒安裝 FFmpeg，無法處理影音檔。');
  if (models.status === 'done') {
    const missing = models.data.models.filter((m) => m.downloadable && !m.installed);
    if (missing.length > 0) problems.push(`還沒下載：${missing.map((m) => m.display_name).join('、')}。`);
  }
  if (problems.length === 0) return null;

  return (
    <div role="alert" className={cn('flex flex-wrap items-center gap-4 rounded-xl bg-chip p-4', className)}>
      <Mono animation="error" scale={1} />
      <div className="min-w-0 flex-1 text-sm">
        {problems.map((p) => (
          <p key={p} className="font-medium">{p}</p>
        ))}
      </div>
      <Button size="sm" onClick={() => setPage('models')}>前往模型管理</Button>
    </div>
  );
}
