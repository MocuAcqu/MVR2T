import { useState } from 'react';
import type { ModelManagerState, UnusedItem } from '@shared/types/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatBytes } from '@/lib/format';
import { deleteUnused } from './modelActions';
import { t } from '@/i18n';

/** 不再使用的檔案：舊版本、之前比較用的模型、中斷留下的暫存（Phase 09 版本管理）。沒有時不顯示。 */
export function UnusedModelsCard({ items, onState }: { items: UnusedItem[]; onState: (s: ModelManagerState) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (items.length === 0) return null;
  const total = items.reduce((s, i) => s + i.size_bytes, 0);

  const remove = async (key: string) => {
    setBusy(key);
    setError(null);
    try {
      onState(await deleteUnused(key));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('不再使用的檔案')}</CardTitle>
        <CardDescription>{t('舊版本的模型或執行程式、之前比較用的模型，或中斷留下的暫存，共 {0}。目前的功能不會用到，可以刪除以節省空間。', formatBytes(total))}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col">
          {items.map((i) => (
            <li key={i.key} className="flex items-center justify-between gap-3 border-t border-chip py-2.5 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">{i.label}</p>
                <p className="text-xs text-body-gray">{i.partial ? t('下載未完成的暫存・') : ''}{formatBytes(i.size_bytes)}</p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => void remove(i.key)} disabled={busy !== null}>
                {busy === i.key ? t('刪除中…') : t('刪除')}
              </Button>
            </li>
          ))}
        </ul>
        {error ? <p role="alert" className="mt-2 text-sm font-medium">{error}</p> : null}
      </CardContent>
    </Card>
  );
}
