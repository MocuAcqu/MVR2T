import { DEFAULT_MODELS } from '@shared/constants/models';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { useUiStore } from '@/stores/uiStore';

/** Real installed-state arrives with the Model Manager (Phase 09); until then nothing is installed. */
export function ModelStatusCard() {
  const setPage = useUiStore((s) => s.setPage);
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI 模型</CardTitle>
        <CardDescription>首次使用前需下載一次，之後完全離線。</CardDescription>
      </CardHeader>
      <CardContent>
        <ul>
          {DEFAULT_MODELS.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-3 border-t border-chip py-3">
              <div className="min-w-0">
                <p className="font-medium">{m.displayName}</p>
                <p className="text-sm text-body-gray">{m.sizeLabel ? `${m.role}，${m.sizeLabel}` : m.role}</p>
              </div>
              <Badge variant="outline">未安裝</Badge>
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter>
        <Button variant="secondary" size="sm" onClick={() => setPage('models')}>前往模型管理</Button>
      </CardFooter>
    </Card>
  );
}
