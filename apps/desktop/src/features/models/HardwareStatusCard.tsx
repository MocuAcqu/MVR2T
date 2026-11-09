import type { ReactNode } from 'react';
import { describeBackend, StatusDot } from '@/components/StatusDot';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useSystemStatus } from '@/hooks/useSystemStatus';

/** "7.1-full_build-www.gyan.dev" → "7.1"；"n6.1.1" → "6.1.1"。 */
function shortVersion(v: string | null): string {
  if (!v) return '';
  const m = /\d+(?:\.\d+)*/.exec(v);
  return m ? m[0] : v;
}

const OS_NAMES: Record<string, string> = { win32: 'Windows', darwin: 'macOS', linux: 'Linux' };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-t border-chip py-3">
      <dt className="text-sm text-body-gray">{label}</dt>
      <dd className="min-w-0 text-right font-medium">{children}</dd>
    </div>
  );
}

export function HardwareStatusCard() {
  const { app, backend, restartBackend, ffmpeg, recheckFfmpeg } = useSystemStatus();
  const ffmpegMissing = ffmpeg.status === 'done' && !ffmpeg.ffmpeg.available;
  const status = describeBackend(backend);
  const system =
    app.status === 'electron'
      ? `${OS_NAMES[app.info.platform] ?? app.info.platform} ${app.info.arch}`
      : app.status === 'browser'
        ? '瀏覽器預覽'
        : '檢查中';

  return (
    <Card>
      <CardHeader>
        <CardTitle>這台電腦</CardTitle>
        <CardDescription>目前的執行環境與本機後端狀態。</CardDescription>
      </CardHeader>
      <CardContent>
        <dl>
          <Row label="作業系統">{system}</Row>
          <Row label="本機後端">
            <span className="inline-flex items-center gap-2">
              <StatusDot state={status.state} />
              {backend.status === 'online' ? `已連線，版本 ${backend.health.version}` : status.label}
            </span>
          </Row>
          <Row label="FFmpeg">
            <span className="inline-flex items-center gap-2">
              <StatusDot
                state={ffmpeg.status === 'done' ? (ffmpeg.ffmpeg.available ? 'ok' : 'fail') : 'pending'}
              />
              {ffmpeg.status === 'done'
                ? ffmpeg.ffmpeg.available
                  ? `已安裝 ${shortVersion(ffmpeg.ffmpeg.version)}`
                  : '未安裝'
                : ffmpeg.status === 'checking'
                  ? '檢查中'
                  : '-'}
            </span>
          </Row>
          <Row label="運算裝置">尚未偵測</Row>
        </dl>

        {ffmpegMissing ? (
          <div role="alert" className="mt-2 flex flex-col gap-3 rounded-lg bg-chip p-4 text-sm">
            <p className="font-medium">需要 FFmpeg 才能處理影音檔。</p>
            <p>
              Windows：在 PowerShell 執行 <code className="rounded bg-background px-1 font-mono">winget install Gyan.FFmpeg</code>，
              完成後按「重新檢查」；若仍偵測不到，請關閉並重新開啟 MVR2T（開發時請一併重開終端機）。
            </p>
            <p>macOS：在終端機執行 <code className="rounded bg-background px-1 font-mono">brew install ffmpeg</code>。</p>
            <Button size="sm" variant="outline" className="self-start" onClick={recheckFfmpeg}>
              重新檢查
            </Button>
          </div>
        ) : null}

        {backend.status === 'error' ? (
          <div role="alert" className="mt-2 flex flex-col gap-3 rounded-lg bg-chip p-4">
            <p className="text-sm font-medium">{backend.message}</p>
            {backend.logTail.length > 0 ? (
              <details className="text-xs text-body-gray">
                <summary className="cursor-pointer rounded-pill font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2">
                  顯示後端輸出
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono">
                  {backend.logTail.join('\n')}
                </pre>
              </details>
            ) : null}
            {restartBackend ? (
              <Button size="sm" className="self-start" onClick={restartBackend}>
                重新啟動後端
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
