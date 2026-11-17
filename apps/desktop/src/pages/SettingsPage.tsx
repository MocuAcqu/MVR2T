import { useId } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Mono } from '@/components/mono/Mono';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ExportFolderSetting } from '@/features/export/ExportFolderSetting';
import { AboutCard, ComputeSettings, RecognitionSettings, StorageSettings } from '@/features/settings/SettingsCards';
import { useGuideStore } from '@/features/guide/guideStore';
import { cn } from '@/lib/utils';

/** 設定（規格 §12.4）：操作引導、語言與預設模型、推論裝置與記憶體、匯出資料夾、暫存清理、關於。 */
export function SettingsPage() {
  const id = useId();
  const enabled = useGuideStore((s) => s.enabled);
  const setEnabled = useGuideStore((s) => s.setEnabled);

  return (
    <PageContainer>
      <h1 className="text-h1">設定</h1>
      <div className="mt-6 grid items-start gap-6 md:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
        <Card>
          <CardHeader className="flex-row items-center gap-4 pb-6">
            <Mono animation="hint" scale={2} />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle id={`${id}-title`}>操作引導</CardTitle>
              <CardDescription>開啟時，每完成一步，下一個按鈕會發光，Mono 會說明接下來要做什麼。不需要時可以在這裡關閉。</CardDescription>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-labelledby={`${id}-title`}
              onClick={() => setEnabled(!enabled)}
              className={cn(
                'relative h-7 w-12 shrink-0 rounded-pill transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2',
                enabled ? 'bg-foreground' : 'bg-hover-gray',
              )}
            >
              <span
                className={cn(
                  'absolute left-0 top-1 size-5 rounded-full bg-background transition-transform',
                  enabled ? 'translate-x-6' : 'translate-x-1',
                )}
              />
            </button>
          </CardHeader>
        </Card>
          <RecognitionSettings />
          <ExportFolderSetting />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <ComputeSettings />
          <StorageSettings />
          <AboutCard />
        </div>
      </div>
    </PageContainer>
  );
}
