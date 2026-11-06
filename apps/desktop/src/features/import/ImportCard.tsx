import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { MediaDropzone } from '@/features/import/MediaDropzone';
import { YouTubeUrlInput } from '@/features/import/YouTubeUrlInput';
import { useUiStore } from '@/stores/uiStore';

export function ImportCard() {
  const setPage = useUiStore((s) => s.setPage);
  return (
    <Card featured>
      <CardHeader>
        <CardTitle className="text-h2">新增影音</CardTitle>
        <CardDescription>匯入本機檔案，或貼上 YouTube 網址。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <MediaDropzone onOpenWorkspace={() => setPage('workspace')} />
        <hr className="border-chip" />
        <YouTubeUrlInput />
      </CardContent>
    </Card>
  );
}
