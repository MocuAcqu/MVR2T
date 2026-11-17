import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { MediaDropzone } from '@/features/import/MediaDropzone';
import { YouTubeUrlInput } from '@/features/import/YouTubeUrlInput';
import { useUiStore } from '@/stores/uiStore';
import { t } from '@/i18n';

export function ImportCard() {
  const setPage = useUiStore((s) => s.setPage);
  return (
    <Card featured>
      <CardHeader>
        <CardTitle className="text-h2">{t('新增影音')}</CardTitle>
        <CardDescription>{t('匯入本機檔案，或貼上 YouTube 網址（只下載音訊）。')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <MediaDropzone onOpenWorkspace={() => setPage('workspace')} />
        <hr className="border-chip" />
        <YouTubeUrlInput />
      </CardContent>
    </Card>
  );
}
