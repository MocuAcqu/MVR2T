import { useState } from 'react';
import type { ModelManagerState, ModelPackage, PackageStatus } from '@shared/types/api';
import { Mono } from '@/components/mono/Mono';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { formatBytes } from '@/lib/format';
import { deletePackage, etaSeconds, formatEta, packageAction, shortRevision } from './modelActions';
import { t } from '@/i18n';

const STATUS: Record<PackageStatus, { label: string; variant: 'solid' | 'outline' | 'default' }> = {
  installed: { label: '已安裝', variant: 'solid' },
  not_installed: { label: '未安裝', variant: 'outline' },
  partial: { label: '下載未完成', variant: 'outline' },
  outdated: { label: '有新版本', variant: 'outline' },
  damaged: { label: '檔案損壞', variant: 'outline' },
  queued: { label: '排隊中', variant: 'default' },
  downloading: { label: '下載中', variant: 'default' },
  verifying: { label: '驗證中', variant: 'default' },
};

const DELETE_WARNING: Record<ModelPackage['id'], string> = {
  asr: '刪除後無法進行語音辨識，需要重新下載（約 3.4 GB）。',
  llm: '刪除後無法產生摘要與心智圖，需要重新下載（約 2.6 GB）。',
  llm_gpu: '刪除後摘要改用 CPU（較慢），之後可以再下載。',
};

/** 一個功能的模型（語音辨識／摘要與心智圖）：狀態、下載進度、驗證、刪除（Phase 09）。 */
export function ModelPackageCard({ pkg, onState }: { pkg: ModelPackage; onState: (s: ModelManagerState) => void }) {
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pending, setPending] = useState(false);
  const status = STATUS[pkg.status];
  const job = pkg.job;
  const running = !!job;
  const runtimeUnsupported = pkg.runtime && !pkg.runtime.installed && !pkg.runtime.supported;

  const run = async (fn: () => Promise<ModelManagerState>) => {
    setError(null);
    setPending(true);
    try {
      onState(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
      setConfirmDelete(false);
    }
  };

  const downloadLabel =
    pkg.status === 'partial'
      ? t('繼續下載（還需 {0}）', formatBytes(pkg.missing_bytes))
      : pkg.status === 'outdated'
        ? t('更新到新版本（最多 {0}）', formatBytes(pkg.missing_bytes))
        : pkg.status === 'damaged'
          ? t('修復（重新下載損壞的檔案）')
          : t('下載（{0}）', formatBytes(pkg.missing_bytes));

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle>{pkg.name}</CardTitle>
          <Badge variant={status.variant} className="shrink-0">{t(status.label)}</Badge>
        </div>
        <CardDescription>{pkg.role}</CardDescription>
        <p className="text-xs text-body-gray">{pkg.hardware}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col">
          {pkg.models.map((m) => (
            <li key={m.id} className="flex items-start justify-between gap-3 border-t border-chip py-2.5 text-sm">
              <div className="min-w-0">
                <p className="font-medium">{m.display_name}</p>
                <p className="text-xs text-body-gray">{t('{0}・{1}・{2}・版本 {3} {4}', m.role, formatBytes(m.size_bytes), m.license, shortRevision(m.revision), m.installed_revision && m.installed_revision !== m.revision ? t('（已安裝舊版 {0}）', shortRevision(m.installed_revision)) : '')}</p>
              </div>
              <span className="shrink-0 text-xs font-medium" aria-label={m.installed ? t('已安裝') : t('未安裝')}>{m.installed ? t('✓ 已安裝') : t('未安裝')}</span>
            </li>
          ))}
          {pkg.runtime ? (
            <li className="flex items-start justify-between gap-3 border-t border-chip py-2.5 text-sm">
              <div className="min-w-0">
                <p className="font-medium">{pkg.runtime.name} {pkg.runtime.version}</p>
                <p className="text-xs text-body-gray">{t('執行摘要模型的程式・{0}・MIT', formatBytes(pkg.runtime.size_bytes))}</p>
              </div>
              <span className="shrink-0 text-xs font-medium">{pkg.runtime.installed ? t('✓ 已安裝') : t('未安裝')}</span>
            </li>
          ) : null}
        </ul>

        {job ? (
          <div className="flex items-end gap-3" aria-live="polite">
            <Mono animation={job.action === 'verify' ? 'video' : 'loading'} scale={1} />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <div className="flex justify-between gap-3 text-sm">
                <span className="truncate font-medium">
                  {job.status === 'queued' ? t('排隊中，等前一個下載完成') : job.cancelling ? t('取消中…') : job.stage}
                  {job.current && job.status !== 'queued' ? <span className="ml-2 font-normal text-body-gray">{job.current}</span> : null}
                </span>
                {job.total_bytes ? <span className="shrink-0 tabular-nums text-body-gray">{Math.floor((job.done_bytes / job.total_bytes) * 100)}%</span> : null}
              </div>
              <Progress label={job.action === 'verify' ? t('驗證進度') : t('下載進度')} value={job.total_bytes ? job.done_bytes / job.total_bytes : 0} />
              {job.total_bytes ? (
                <p className="text-xs tabular-nums text-body-gray">
                  {formatBytes(job.done_bytes)} / {formatBytes(job.total_bytes)}
                  {job.action === 'download' && job.speed > 0 ? `・${formatBytes(job.speed)}/s・${formatEta(etaSeconds(job.done_bytes, job.total_bytes, job.speed))}` : ''}
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {!job && pkg.last ? (
          <div role={pkg.last.ok ? 'status' : 'alert'} className="rounded-lg bg-chip px-4 py-3 text-sm">
            <p className="font-medium">{pkg.last.message}</p>
            {pkg.last.problems.length ? (
              <ul className="mt-1 list-disc pl-5 text-body-gray">
                {pkg.last.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {runtimeUnsupported ? <p className="text-sm text-body-gray">{t('這個作業系統目前沒有可用的 llama.cpp 執行檔。')}</p> : null}
        {error ? <p role="alert" className="text-sm font-medium">{error}</p> : null}
      </CardContent>
      <CardFooter className="flex-wrap">
        {confirmDelete ? (
          <>
            <p className="w-full text-sm">{t('{0}確定刪除嗎？', t(DELETE_WARNING[pkg.id]))}</p>
            <Button onClick={() => void run(() => deletePackage(pkg.id))} disabled={pending}>{t('確定刪除')}</Button>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>{t('取消')}</Button>
          </>
        ) : running ? (
          <Button variant="secondary" onClick={() => void run(() => packageAction(pkg.id, 'cancel'))} disabled={pending || job?.cancelling}>
            {job?.action === 'verify' ? t('停止驗證') : t('取消下載')}
          </Button>
        ) : pkg.status === 'installed' ? (
          <>
            <Button variant="secondary" onClick={() => void run(() => packageAction(pkg.id, 'verify'))} disabled={pending}>{t('驗證完整性')}</Button>
            <Button variant="ghost" onClick={() => setConfirmDelete(true)} disabled={pending}>{t('刪除')}</Button>
          </>
        ) : (
          <>
            <Button onClick={() => void run(() => packageAction(pkg.id, 'download'))} disabled={pending || !!runtimeUnsupported}>{downloadLabel}</Button>
            {pkg.status === 'damaged' || pkg.status === 'partial' || pkg.status === 'outdated' ? (
              <Button variant="ghost" onClick={() => setConfirmDelete(true)} disabled={pending}>{t('刪除')}</Button>
            ) : null}
          </>
        )}
      </CardFooter>
    </Card>
  );
}
