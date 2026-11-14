import { useCallback, useEffect, useState, type ReactNode } from 'react';
import type { ComputeDevice, SystemInfo } from '@shared/types/api';
import { describeBackend, StatusDot } from '@/components/StatusDot';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { formatBytes } from '@/lib/format';
import { getBackendConnection, getSystemInfo } from '@/services/api';

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
      <dt className="shrink-0 whitespace-nowrap text-sm text-body-gray">{label}</dt>
      <dd className="min-w-0 text-right font-medium">{children}</dd>
    </div>
  );
}

const DEVICE: Record<ComputeDevice, string> = { cpu: 'CPU', cuda: 'NVIDIA GPU（CUDA）', metal: 'Apple GPU（Metal）' };

/** 硬體資訊與運算裝置（GET /api/system/info，Phase 10）。後端連線後讀一次；「重新偵測」會重新找顯示卡。 */
function useSystemInfo(backendKey: string | null) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async (refresh: boolean) => {
    const conn = await getBackendConnection();
    if (!conn) return;
    setLoading(true);
    try {
      setInfo(await getSystemInfo(conn, refresh));
    } catch {
      setInfo(null);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (backendKey) void load(false);
    else setInfo(null);
  }, [backendKey, load]);
  return { info, loading, redetect: () => void load(true) };
}

export function HardwareStatusCard() {
  const { app, backend, restartBackend, ffmpeg, recheckFfmpeg } = useSystemStatus();
  const { info, loading, redetect } = useSystemInfo(backend.status === 'online' ? backend.backendUrl : null);
  const hw = info?.hardware;
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
          {hw ? (
            <>
              <Row label="處理器">
                <span className="block break-words">{hw.cpu_name}</span>
                <span className="block text-xs font-normal text-body-gray">{hw.cpu_threads} 執行緒</span>
              </Row>
              <Row label="記憶體">
                {formatBytes(hw.ram_total)}
                <span className="block text-xs font-normal text-body-gray">目前可用 {formatBytes(hw.ram_available)}</span>
              </Row>
              <Row label="顯示卡">
                {hw.gpus.length === 0 ? (
                  '未偵測到'
                ) : (
                  hw.gpus.map((g) => (
                    <span key={g.name} className="block">
                      {g.name}
                      {g.vram_total ? <span className="text-xs font-normal text-body-gray">（{formatBytes(g.vram_total)}）</span> : null}
                    </span>
                  ))
                )}
              </Row>
              <Row label={hw.platform === 'darwin' ? 'Metal' : 'CUDA'}>
                <span className="inline-flex items-center gap-2">
                  <StatusDot state={(hw.platform === 'darwin' ? hw.metal_available : hw.cuda_available) ? 'ok' : 'pending'} />
                  {(hw.platform === 'darwin' ? hw.metal_available : hw.cuda_available) ? '可用' : '不可用'}
                </span>
                <span className="block text-xs font-normal text-body-gray">{hw.platform === 'darwin' ? hw.metal_reason : hw.cuda_reason}</span>
              </Row>
              <Row label="運算裝置">
                <span className="block">語音辨識：{DEVICE[info.asr.device]}</span>
                <span className="block">摘要：{DEVICE[info.llm.device]}</span>
                <span className="block text-xs font-normal text-body-gray">{info.llm.reason}</span>
              </Row>
            </>
          ) : (
            <Row label="運算裝置">{backend.status === 'online' ? (loading ? '偵測中…' : '無法取得') : '-'}</Row>
          )}
        </dl>
        {info && [...info.llm.warnings, ...info.asr.warnings].length > 0 ? (
          <div role="status" className="mt-2 flex flex-col gap-1 rounded-lg bg-chip p-4 text-sm">
            {[...info.llm.warnings, ...info.asr.warnings].map((w) => (
              <p key={w}>{w}</p>
            ))}
          </div>
        ) : null}
        {hw ? (
          <Button size="sm" variant="secondary" className="mt-3" onClick={redetect} disabled={loading}>
            {loading ? '偵測中…' : '重新偵測'}
          </Button>
        ) : null}

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
