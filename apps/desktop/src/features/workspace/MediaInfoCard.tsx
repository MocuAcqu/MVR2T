import type { MediaInfo } from '@shared/types/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatBytes, formatDuration } from '@/lib/format';

const channelLabel = (n: number | null) => (n === 1 ? '單聲道' : n === 2 ? '立體聲' : n ? `${n} 聲道` : '-');

/** 後端以 ffprobe 實際讀到的影音資訊（規格 §2.1-A：檔名、格式、大小、長度）。 */
export function MediaInfoCard({ info }: { info: MediaInfo }) {
  const rows: [string, string][] = [
    ['檔名', info.filename],
    ...(info.origin === 'youtube'
      ? ([['來源', 'YouTube（只下載音訊）'], ...(info.source_url ? [['網址', info.source_url]] : [])] as [string, string][])
      : []),
    ['類型', info.kind === 'audio' ? '音訊' : '影片'],
    ['格式', info.format.toUpperCase()],
    ['大小', formatBytes(info.size)],
    ['長度', formatDuration(info.duration)],
    [
      '音訊',
      [info.audio_codec?.toUpperCase(), info.sample_rate ? `${(info.sample_rate / 1000).toFixed(1)} kHz` : null, channelLabel(info.channels)]
        .filter(Boolean)
        .join('，'),
    ],
  ];
  if (info.has_video) {
    rows.push(['影像', [info.video_codec?.toUpperCase(), info.width && info.height ? `${info.width} x ${info.height}` : null].filter(Boolean).join('，')]);
  }
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle>影音資訊</CardTitle>
        <CardDescription>{info.origin === 'youtube' ? '已下載到本次工作階段' : '已複製到本次工作階段'}，結束後自動刪除。</CardDescription>
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
