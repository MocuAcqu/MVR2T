import type { MediaInfo } from '@shared/types/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatBytes, formatDuration } from '@/lib/format';
import { t } from '@/i18n';

const channelLabel = (n: number | null) => (n === 1 ? t('單聲道') : n === 2 ? t('立體聲') : n ? t('{0} 聲道', n) : '-');

/** 後端以 ffprobe 實際讀到的影音資訊（規格 §2.1-A：檔名、格式、大小、長度）。 */
export function MediaInfoCard({ info }: { info: MediaInfo }) {
  const rows: [string, string][] = [
    [t('檔名'), info.filename],
    ...(info.origin === 'youtube'
      ? ([[t('來源'), t('YouTube（只下載音訊）')], ...(info.source_url ? [[t('網址'), info.source_url]] : [])] as [string, string][])
      : []),
    [t('類型'), info.kind === 'audio' ? t('音訊') : t('影片')],
    [t('格式'), info.format.toUpperCase()],
    [t('大小'), formatBytes(info.size)],
    [t('長度'), formatDuration(info.duration)],
    [
      t('音訊'),
      [info.audio_codec?.toUpperCase(), info.sample_rate ? `${(info.sample_rate / 1000).toFixed(1)} kHz` : null, channelLabel(info.channels)]
        .filter(Boolean)
        .join(t('，')),
    ],
  ];
  if (info.has_video) {
    rows.push([t('影像'), [info.video_codec?.toUpperCase(), info.width && info.height ? `${info.width} x ${info.height}` : null].filter(Boolean).join(t('，'))]);
  }
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle>{t('影音資訊')}</CardTitle>
        <CardDescription>{t('{0}，結束後自動刪除。', info.origin === 'youtube' ? t('已下載到本次工作階段') : t('已複製到本次工作階段'))}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4 border-t border-chip py-3">
              <dt className="shrink-0 text-body-gray">{k}</dt>
              <dd className="min-w-0 break-all text-right font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
