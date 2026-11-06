import { getExtension, getMediaKind } from '@shared/constants/media';
import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { formatBytes } from '@/lib/format';
import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';

/** Placeholder workspace: shows the imported file. Processing arrives with the media/ASR phases. */
export function WorkspacePage() {
  const media = useSessionStore((s) => s.media);
  const setMedia = useSessionStore((s) => s.setMedia);
  const setPage = useUiStore((s) => s.setPage);

  return (
    <PageContainer>
      <h1 className="text-h1">工作區</h1>
      <Card className="mt-6 max-w-xl">
        {media ? (
          <>
            <CardHeader>
              <CardTitle>已匯入的檔案</CardTitle>
              <CardDescription>音訊抽取、語音辨識與逐字稿編輯將在後續版本於此提供。</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="text-sm">
                {[
                  ['檔名', media.name],
                  ['類型', getMediaKind(media.name) === 'audio' ? '音訊' : '影片'],
                  ['格式', getExtension(media.name).toUpperCase()],
                  ['大小', formatBytes(media.size)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 border-t border-chip py-3">
                    <dt className="text-body-gray">{k}</dt>
                    <dd className="min-w-0 break-all text-right font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
            <CardFooter>
              <Button variant="secondary" onClick={() => { setMedia(null); setPage('dashboard'); }}>換一個檔案</Button>
            </CardFooter>
          </>
        ) : (
          <>
            <CardHeader>
              <CardTitle>還沒有匯入影音</CardTitle>
              <CardDescription>回到首頁匯入影片或錄音，就能在這裡處理。</CardDescription>
            </CardHeader>
            <CardFooter>
              <Button onClick={() => setPage('dashboard')}>回到首頁</Button>
            </CardFooter>
          </>
        )}
      </Card>
    </PageContainer>
  );
}
