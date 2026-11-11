import { useEffect, useState } from 'react';
import type { ExportPrefs } from '@shared/types/ipc';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';

/** 設定：固定的匯出資料夾。只存資料夾路徑（不存任何內容），存在 Main 的偏好檔。 */
export function ExportFolderSetting() {
  const bridge = typeof window !== 'undefined' ? window.mvr2t : undefined;
  const [prefs, setPrefs] = useState<ExportPrefs | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void bridge?.getExportPrefs?.().then(setPrefs).catch(() => undefined);
  }, [bridge]);

  const run = async (fn: () => Promise<ExportPrefs>) => {
    setBusy(true);
    try {
      setPrefs(await fn());
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>匯出資料夾</CardTitle>
        <CardDescription>指定後，匯出時直接存到這個資料夾，不再詢問（匯出面板中仍可改選其他資料夾）。沒有指定時每次詢問，並從上次選的資料夾開始。</CardDescription>
      </CardHeader>
      <CardContent>
        {!bridge?.getExportPrefs ? (
          <p className="text-sm text-body-gray">這項設定需要在桌面程式中使用。</p>
        ) : !prefs ? null : prefs.fixedFolder ? (
          <div className="rounded-lg bg-chip px-4 py-3 text-sm">
            <p className="break-all font-medium">{prefs.fixedFolder}</p>
            {!prefs.fixedFolderAvailable ? <p className="mt-1 text-body-gray">目前找不到這個資料夾（例如外接硬碟沒有接上），匯出時會改為詢問。</p> : null}
          </div>
        ) : (
          <p className="text-sm text-body-gray">
            目前：每次詢問{prefs.lastFolder ? <>（上次：<span className="break-all">{prefs.lastFolder}</span>）</> : null}
          </p>
        )}
      </CardContent>
      {bridge?.getExportPrefs && prefs ? (
        <CardFooter className="flex-wrap">
          <Button variant={prefs.fixedFolder ? 'secondary' : 'default'} disabled={busy} onClick={() => void run(() => bridge.chooseFixedExportFolder())}>
            {prefs.fixedFolder ? '更換資料夾…' : '指定資料夾…'}
          </Button>
          {prefs.fixedFolder ? (
            <Button variant="ghost" disabled={busy} onClick={() => void run(() => bridge.clearFixedExportFolder())}>
              改為每次詢問
            </Button>
          ) : null}
        </CardFooter>
      ) : null}
    </Card>
  );
}
