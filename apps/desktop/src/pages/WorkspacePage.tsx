import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { removeMedia } from '@/features/media/mediaController';
import { ExtractionCard } from '@/features/workspace/ExtractionCard';
import { MediaInfoCard } from '@/features/workspace/MediaInfoCard';
import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';

/** Media workspace. Phase 04: media info + audio extraction and segmentation. Transcript etc. come later. */
export function WorkspacePage() {
  const imp = useSessionStore((s) => s.import);
  const setPage = useUiStore((s) => s.setPage);

  if (imp.status !== 'ready') {
    const inProgress = imp.status === 'uploading' || imp.status === 'probing';
    return (
      <PageContainer>
        <h1 className="text-h1">工作區</h1>
        <Card className="mt-6 max-w-xl">
          <CardHeader>
            <CardTitle>{inProgress ? '檔案匯入中' : '還沒有匯入影音'}</CardTitle>
            <CardDescription>
              {inProgress ? '請回到首頁查看匯入進度。' : '回到首頁匯入影片或錄音，就能在這裡處理。'}
            </CardDescription>
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
      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <MediaInfoCard info={imp.info} />
        <ExtractionCard />
      </div>
    </PageContainer>
  );
}
