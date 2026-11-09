import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { KeepAwakeNote } from '@/features/media/KeepAwakeNote';
import { cancelExtraction, removeMedia, startExtraction } from '@/features/media/mediaController';
import { GuideCoach } from '@/features/guide/GuideCoach';
import { GuideTarget } from '@/features/guide/GuideTarget';
import { SegmentTable } from '@/features/workspace/SegmentTable';
import { formatDuration, formatPercent } from '@/lib/format';
import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';

/** 抽取音訊（16 kHz 單聲道）並依停頓切段；顯示整體與目前步驟的進度，可取消（規格 §9.2）。 */
export function ExtractionCard() {
  const x = useSessionStore((s) => s.extraction);
  const setPage = useUiStore((s) => s.setPage);
  const busy = x.status === 'starting' || x.status === 'queued' || x.status === 'running';
  const stopped = x.status === 'cancelled' || x.status === 'failed';
  const changeFile = () => {
    void removeMedia();
    setPage('dashboard');
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle>音訊抽取與切段</CardTitle>
        <CardDescription>轉成語音辨識用的 16 kHz 單聲道音訊，並在說話停頓處切成約 30 秒的片段。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        {busy ? (
          <div className="flex items-end gap-4">
          {/* 處理音訊時，Mono 戴耳機聽 */}
          <Mono animation="music" scale={2} />
          <div className="flex min-w-0 flex-1 flex-col gap-2" aria-live="polite">
            <div className="flex justify-between gap-4 text-sm">
              <span className="font-medium">
                {x.stage || '準備中'}
                {x.detail ? <span className="ml-2 font-normal text-body-gray">{x.detail}</span> : null}
              </span>
              <span className="tabular-nums text-body-gray">{formatPercent(x.progress)}</span>
            </div>
            <Progress label="音訊抽取進度" value={x.progress} />
            <KeepAwakeNote />
          </div>
          </div>
        ) : null}

        {x.status === 'completed' && x.result ? (
          <>
            <p className="text-sm" role="status">
              完成：共 <span className="font-medium">{x.result.segments.length}</span> 段，總長{' '}
              <span className="font-medium">{formatDuration(x.result.duration)}</span>，
              {(x.result.sample_rate / 1000).toFixed(0)} kHz {x.result.channels === 1 ? '單聲道' : `${x.result.channels} 聲道`}。
            </p>
            <SegmentTable segments={x.result.segments} />
          </>
        ) : null}

        {x.status === 'failed' ? (
          <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
            <Mono animation="error" scale={1} />
            <p role="alert" className="text-sm font-medium">{x.message ?? '音訊抽取失敗。'}</p>
          </div>
        ) : null}
        {x.status === 'cancelled' ? (
          <p role="status" className="text-sm text-body-gray">已取消，暫存的音訊已刪除。可以再試一次，或換一個檔案。</p>
        ) : null}
        <GuideCoach step="extract" className="mt-auto" />
      </CardContent>
      <CardFooter>
        {busy ? (
          <Button variant="secondary" onClick={() => void cancelExtraction()} disabled={x.status === 'starting'}>
            取消
          </Button>
        ) : (
          <>
            <GuideTarget step="extract">
              <Button onClick={() => void startExtraction()}>
                {x.status === 'completed' ? '重新抽取' : x.status === 'idle' ? '抽取音訊' : '再試一次'}
              </Button>
            </GuideTarget>
            {/* 取消或失敗後，直接在這裡提供「換一個檔案」，不必找頁面右上角的按鈕 */}
            {stopped ? (
              <Button variant="secondary" onClick={changeFile}>
                換一個檔案
              </Button>
            ) : null}
          </>
        )}
      </CardFooter>
    </Card>
  );
}
