import { useEffect, useRef } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { ExportDialog } from '@/features/export/ExportDialog';
import { useExportUi } from '@/features/export/exportStore';
import { removeMedia } from '@/features/media/mediaController';
import { ExtractionCard } from '@/features/workspace/ExtractionCard';
import { MindMapCard } from '@/features/mindmap/MindMapCard';
import { PlayerCard } from '@/features/player/PlayerCard';
import { MediaInfoCard } from '@/features/workspace/MediaInfoCard';
import { SummaryCard } from '@/features/workspace/SummaryCard';
import { TranscriptCard } from '@/features/workspace/TranscriptCard';
import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';

/** Media workspace: media info, audio extraction (Phase 04), transcript (Phase 05), summary (Phase 06), mind map (Phase 07). */
export function WorkspacePage() {
  const imp = useSessionStore((s) => s.import);
  const focus = useUiStore((s) => s.focus);
  const transcriptRef = useRef<HTMLDivElement>(null);
  // 用影片字幕匯入完成後直接跳到逐字稿（2026-11-17 使用者建議）
  useEffect(() => {
    if (focus !== 'transcript' || imp.status !== 'ready') return;
    // 等版面排好（AppShell 的「換頁回到頂端」會略過有 focus 的換頁）
    const timer = window.setTimeout(() => {
      transcriptRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      useUiStore.getState().clearFocus();
    }, 100);
    return () => window.clearTimeout(timer);
  }, [focus, imp.status]);
  const setPage = useUiStore((s) => s.setPage);
  const openExport = useExportUi((s) => s.openPanel);

  if (imp.status !== 'ready') {
    const inProgress = imp.status === 'uploading' || imp.status === 'probing';
    return (
      <PageContainer>
        <h1 className="text-h1">工作區</h1>
        <Card className="mt-6 max-w-xl">
          <CardHeader className="flex-row items-end gap-4">
            <Mono animation={inProgress ? 'loading' : 'idle'} scale={2} interactive />
            <div className="flex flex-col gap-1.5">
            <CardTitle>{inProgress ? '檔案匯入中' : '還沒有匯入影音'}</CardTitle>
            <CardDescription>
              {inProgress ? '請回到首頁查看匯入進度。' : '回到首頁匯入影片或錄音，就能在這裡處理。'}
            </CardDescription>
            </div>
          </CardHeader>
          <CardFooter>
            <Button onClick={() => setPage('dashboard')}>回到首頁</Button>
          </CardFooter>
        </Card>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-h1">工作區</h1>
          <p className="mt-1 truncate text-body-gray" title={imp.info.filename}>{imp.info.filename}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => openExport()} title="一次匯出切段、逐字稿、摘要與心智圖">匯出</Button>
          <Button
            variant="secondary"
            onClick={() => {
              void removeMedia();
              setPage('dashboard');
            }}
          >
            換一個檔案
          </Button>
        </div>
      </div>
      {/* items-stretch（預設）：兩張卡片在同一列時等高 */}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <MediaInfoCard info={imp.info} />
        <ExtractionCard />
      </div>
      <div className="mt-6">
        <PlayerCard info={imp.info} />
      </div>
      <div className="mt-6 scroll-mt-24" ref={transcriptRef}>
        <TranscriptCard />
      </div>
      <div className="mt-6">
        <SummaryCard />
      </div>
      <div className="mt-6">
        <MindMapCard />
      </div>
      <ExportDialog />
    </PageContainer>
  );
}
