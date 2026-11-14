import { useState } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Button } from '@/components/ui/button';
import { HardwareStatusCard } from '@/features/models/HardwareStatusCard';
import { ModelPackageCard } from '@/features/models/ModelPackageCard';
import { UnusedModelsCard } from '@/features/models/UnusedModelsCard';
import { downloadAll } from '@/features/models/modelActions';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { formatBytes } from '@/lib/format';

/** 模型管理（Phase 09）：下載（進度、取消、續傳）、驗證、刪除、版本更新、清除不再使用的檔案。 */
export function ModelsPage() {
  const { models, applyModels } = useSystemStatus();
  const [error, setError] = useState<string | null>(null);
  const data = models.status === 'done' ? models.data : null;
  const missing = data ? data.packages.filter((p) => !p.optional && p.status !== 'installed' && !p.job) : [];
  const missingBytes = missing.reduce((s, p) => s + p.missing_bytes, 0);

  return (
    <PageContainer>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-h1">模型管理</h1>
          <p className="mt-1 text-body-gray">AI 模型只需下載一次，之後完全離線使用；只有在這裡按下下載時才會連網。</p>
        </div>
        {missing.length > 1 ? (
          <Button
            onClick={() => {
              setError(null);
              downloadAll()
                .then(applyModels)
                .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
            }}
          >
            全部下載（{formatBytes(missingBytes)}）
          </Button>
        ) : null}
      </div>
      {data ? (
        <p className="mt-2 text-sm text-body-gray">
          存放位置：<span className="break-all">{data.models_dir}</span>・剩餘空間 {formatBytes(data.free_bytes)}
        </p>
      ) : null}
      {error ? <p role="alert" className="mt-2 text-sm font-medium">{error}</p> : null}

      {!data ? (
        <p className="mt-6 text-sm text-body-gray">{models.status === 'loading' ? '讀取中…' : '等待本機後端連線。'}</p>
      ) : null}
      {/* 兩個獨立的欄，各自往下排，不會因為另一欄的卡片比較高而留下空白（2026-11-14 使用者建議）：
          左欄：語音辨識＋這台電腦；右欄：摘要與心智圖（＋GPU 加速）＋不再使用的檔案 */}
      <div className="mt-6 grid items-start gap-6 md:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-6">
          {data?.packages.filter((p) => p.id === 'asr').map((p) => <ModelPackageCard key={p.id} pkg={p} onState={applyModels} />)}
          <HardwareStatusCard />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          {data?.packages.filter((p) => p.id !== 'asr').map((p) => <ModelPackageCard key={p.id} pkg={p} onState={applyModels} />)}
          {data ? <UnusedModelsCard items={data.unused} onState={applyModels} /> : null}
        </div>
      </div>
    </PageContainer>
  );
}
