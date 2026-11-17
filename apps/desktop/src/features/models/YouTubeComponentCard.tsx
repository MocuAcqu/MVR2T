import { useCallback, useEffect, useState } from 'react';
import type { YtDlpState } from '@shared/types/api';
import { Mono } from '@/components/mono/Mono';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useYouTubeStore } from '@/features/youtube/youtubeController';
import { formatBytes } from '@/lib/format';
import { deleteYtDlp, getBackendConnection, getYtDlp, ytDlpAction } from '@/services/api';

const POLL_MS = 700;
const PHASE: Record<NonNullable<YtDlpState['job']>['phase'], string> = {
  checking: '查詢最新版本',
  downloading: '下載中',
  installing: '驗證並安裝',
};

async function conn() {
  const c = await getBackendConnection();
  if (!c) throw new Error('本機後端尚未連線。');
  return c;
}

/** YouTube 下載元件（yt-dlp）：按需下載、檢查並更新到官方最新版（例外於「依賴至少 2 週」規則）、刪除。 */
export function YouTubeComponentCard() {
  const [state, setState] = useState<YtDlpState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const apply = useCallback((s: YtDlpState) => {
    setState(s);
    useYouTubeStore.getState().set({ component: s }); // 首頁的 YouTube 區塊同步
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const s = await getYtDlp(await conn());
        if (!alive) return;
        apply(s);
        if (s.job) timer = setTimeout(() => void tick(), POLL_MS);
      } catch {
        if (alive) timer = setTimeout(() => void tick(), 2000);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [apply, state?.job?.phase]);

  const run = async (fn: () => Promise<YtDlpState | void>) => {
    setError(null);
    try {
      const s = await fn();
      apply(s ?? (await getYtDlp(await conn())));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setConfirmDelete(false);
    }
  };

  const job = state?.job ?? null;
  const installed = !!state?.installed;

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle>YouTube 下載元件</CardTitle>
          {state ? (
            <Badge variant={installed ? 'solid' : 'outline'} className="shrink-0">
              {job ? PHASE[job.phase] : installed ? (state.update_available ? '有新版本' : '已安裝') : '未安裝'}
            </Badge>
          ) : null}
        </div>
        <CardDescription>
          貼上 YouTube 網址時，只下載影片的音訊（與作者提供的字幕），之後在這台電腦上辨識與摘要。使用 yt-dlp（{state?.license ?? 'Unlicense'}）。
        </CardDescription>
        <p className="text-xs text-body-gray">
          需要網路。YouTube 經常改版，舊版本可能無法下載：無法下載時請先「檢查更新」。更新一律取官方最新版並驗證 SHA-256。
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!state ? <p className="text-sm text-body-gray">讀取中…</p> : null}
        {state && !state.supported ? <p className="text-sm">這個作業系統沒有官方的 yt-dlp 執行檔。</p> : null}
        {state && installed ? (
          <p className="text-sm">
            目前版本 <span className="font-medium tabular-nums">{state.version}</span>
            {state.latest_version ? <span className="text-body-gray">・最新版本 {state.latest_version}</span> : null}
          </p>
        ) : null}

        {job ? (
          <div className="flex items-end gap-3" aria-live="polite">
            <Mono animation="loading" scale={1} />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <div className="flex justify-between gap-3 text-sm">
                <span className="font-medium">{job.cancelling ? '取消中…' : PHASE[job.phase]}</span>
                {job.total_bytes ? <span className="tabular-nums text-body-gray">{Math.floor((job.done_bytes / job.total_bytes) * 100)}%</span> : null}
              </div>
              <Progress label="YouTube 下載元件進度" value={job.total_bytes ? job.done_bytes / job.total_bytes : 0} indeterminate={!job.total_bytes} />
              {job.total_bytes ? (
                <p className="text-xs tabular-nums text-body-gray">{formatBytes(job.done_bytes)} / {formatBytes(job.total_bytes)}</p>
              ) : null}
            </div>
          </div>
        ) : null}

        {!job && state?.last ? (
          <p role={state.last.ok ? 'status' : 'alert'} className="rounded-lg bg-chip px-4 py-3 text-sm font-medium">{state.last.message}</p>
        ) : null}
        {error ? <p role="alert" className="text-sm font-medium">{error}</p> : null}
        {confirmDelete ? (
          <div role="alertdialog" aria-label="確認刪除" className="flex flex-col gap-3 rounded-lg bg-chip p-4 text-sm">
            <p>刪除後無法使用 YouTube 連結，之後可以再下載。</p>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => void run(async () => deleteYtDlp(await conn()))}>刪除</Button>
              <Button size="sm" variant="secondary" onClick={() => setConfirmDelete(false)}>取消</Button>
            </div>
          </div>
        ) : null}
      </CardContent>
      {state?.supported ? (
        <CardFooter className="flex-wrap gap-2">
          {job ? (
            <Button variant="secondary" disabled={job.cancelling || job.phase !== 'downloading'} onClick={() => void run(async () => ytDlpAction(await conn(), 'cancel'))}>
              取消
            </Button>
          ) : installed ? (
            <>
              {state.update_available ? (
                <Button onClick={() => void run(async () => ytDlpAction(await conn(), 'install'))}>更新到 {state.latest_version}</Button>
              ) : (
                <Button variant="secondary" onClick={() => void run(async () => ytDlpAction(await conn(), 'check'))}>檢查更新</Button>
              )}
              <Button variant="ghost" className="ml-auto" onClick={() => setConfirmDelete(true)}>刪除</Button>
            </>
          ) : (
            <Button onClick={() => void run(async () => ytDlpAction(await conn(), 'install'))}>
              下載{state.size_bytes ? `（${formatBytes(state.size_bytes)}）` : '（約 20 MB）'}
            </Button>
          )}
        </CardFooter>
      ) : null}
    </Card>
  );
}
