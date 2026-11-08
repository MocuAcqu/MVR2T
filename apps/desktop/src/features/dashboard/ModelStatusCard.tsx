import type { ModelInfo } from '@shared/types/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { formatBytes } from '@/lib/format';
import { useUiStore } from '@/stores/uiStore';

function StatusBadge({ m }: { m: ModelInfo }) {
  if (!m.downloadable) return <Badge variant="outline">Phase {m.available_from_phase} 推出</Badge>;
  return m.installed ? <Badge variant="solid">已安裝</Badge> : <Badge variant="outline">未安裝</Badge>;
}

/** 模型清單與安裝狀態來自後端（GET /api/models）；模型 ID 與版本只定義在後端的登錄表。 */
export function ModelStatusCard() {
  const setPage = useUiStore((s) => s.setPage);
  const { models, refreshModels } = useSystemStatus();
  const list = models.status === 'done' ? models.data.models : [];
  const missing = list.filter((m) => m.downloadable && !m.installed);

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI 模型</CardTitle>
        <CardDescription>首次使用前需下載一次，之後完全離線。</CardDescription>
      </CardHeader>
      <CardContent>
        {models.status !== 'done' ? (
          <p className="border-t border-chip py-3 text-sm text-body-gray">{models.status === 'loading' ? '檢查中…' : '等待本機後端連線。'}</p>
        ) : (
          <ul>
            {list.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 border-t border-chip py-3">
                <div className="min-w-0">
                  <p className="font-medium">{m.display_name}</p>
                  <p className="text-sm text-body-gray">
                    {m.role}
                    {m.size_bytes > 0 ? `，${formatBytes(m.size_bytes)}` : ''}
                  </p>
                </div>
                <StatusBadge m={m} />
              </li>
            ))}
          </ul>
        )}
        {missing.length > 0 ? (
          <div className="mt-2 flex flex-col gap-2 rounded-lg bg-chip p-4 text-sm">
            <p className="font-medium">尚未下載：{missing.map((m) => m.display_name).join('、')}</p>
            <p>
              開發階段請在 <code className="rounded bg-background px-1 font-mono">apps\backend</code> 執行{' '}
              <code className="rounded bg-background px-1 font-mono">.\.venv\Scripts\python.exe -m scripts.download_models</code>
              ，完成後按「重新檢查」。程式內的下載功能將在模型管理（Phase 09）提供。
            </p>
          </div>
        ) : null}
      </CardContent>
      <CardFooter>
        <Button variant="secondary" size="sm" onClick={() => setPage('models')}>前往模型管理</Button>
        {models.status === 'done' ? (
          <Button variant="ghost" size="sm" onClick={refreshModels}>重新檢查</Button>
        ) : null}
      </CardFooter>
    </Card>
  );
}
