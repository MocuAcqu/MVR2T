import { useEffect, useRef, useState } from 'react';
import { EXPORT_FORMATS } from '@shared/constants/app';
import type { SummaryType } from '@shared/types/api';
import type { ExportFormat, ExportItemResult, ExportPrefs } from '@shared/types/ipc';
import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { captureMindmap } from '@/features/mindmap/capture';
import { dataUrlPayload } from '@/features/mindmap/exportImage';
import { toSummary } from '@/features/mindmap/model';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { SUMMARY_TYPES } from '@/features/workspace/SummaryCard';
import { useSessionStore } from '@/stores/sessionStore';
import {
  DEFAULT_SELECTION,
  EXPORT_ROWS,
  FORMAT_LABELS,
  estimateZipBytes,
  needsMindmapImage,
  presetSelection,
  selectedItems,
  toggleFormat,
  unavailableReason,
  type Availability,
  type Selection,
} from './exportPlan';
import { useExportUi } from './exportStore';

// 勾選只記在這次開啟的程式中（不寫入任何儲存空間）
let rememberedSelection: Selection = DEFAULT_SELECTION;

type Phase = { kind: 'choose' } | { kind: 'running'; step: string } | { kind: 'done'; folder: string; results: ExportItemResult[] } | { kind: 'error'; message: string };

const fileName = (p: string) => p.split(/[\\/]/).pop() ?? p;

const SUMMARY_LABEL = Object.fromEntries(SUMMARY_TYPES.map((t) => [t.value, t.label])) as Record<SummaryType, string>;

/**
 * 「匯出」面板（Phase 08）：勾選內容與格式 → 選資料夾（或設定中的固定資料夾）→ 一次寫入。
 * 右上角的「匯出」打開完整面板；各卡片的「匯出」打開同一個面板，只預先勾選那張卡片的內容。
 */
export function ExportDialog() {
  const { open, focus, close: onClose } = useExportUi();
  const ref = useRef<HTMLDialogElement>(null);
  const s = useSessionStore();
  const [sel, setSel] = useState<Selection>(rememberedSelection);
  const [phase, setPhase] = useState<Phase>({ kind: 'choose' });
  const [summaryTypes, setSummaryTypes] = useState<SummaryType[]>([]);
  const [prefs, setPrefs] = useState<ExportPrefs | null>(null);
  const [askFolder, setAskFolder] = useState(false);

  // 摘要中有內容的類型（心智圖用目前編輯後的版本）
  const availableSummaryTypes: SummaryType[] = [
    ...(s.summary?.types.filter((t) => t !== 'mindmap') ?? []),
    ...(s.mindmap ? (['mindmap'] as SummaryType[]) : []),
  ];

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setPhase({ kind: 'choose' });
      setSel(focus ? presetSelection(focus, rememberedSelection) : rememberedSelection);
      setSummaryTypes(availableSummaryTypes); // 預設全選
      setAskFolder(false);
      setPrefs(null);
      void window.mvr2t?.getExportPrefs?.().then(setPrefs).catch(() => undefined);
      d.showModal();
    } else if (!open && d.open) d.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const availability: Availability = {
    segments: s.extraction.status === 'completed' && !!s.extraction.result,
    transcript: !!s.transcript && s.transcript.segments.length > 0,
    summary: !!s.summary,
    mindmap: !!s.mindmap,
  };
  const items = selectedItems(sel, availability);
  const exportsSummary = items.some((i) => i.content === 'summary');
  const noSummaryType = exportsSummary && summaryTypes.length === 0;
  const allSummaryTypes = availableSummaryTypes.every((t) => summaryTypes.includes(t));
  const useFixed = !!prefs?.fixedFolder && prefs.fixedFolderAvailable && !askFolder;
  const inElectron = !!window.mvr2t?.exportFiles;
  const running = phase.kind === 'running';
  const duration = s.import.status === 'ready' ? s.import.info.duration : 0;

  const update = (next: Selection) => {
    // 從卡片打開時，只更新那張卡片的內容的記憶，不清掉其他內容之前的勾選
    rememberedSelection = focus ? { ...rememberedSelection, ...next } : next;
    setSel(next);
  };
  const toggleSummaryType = (t: SummaryType) =>
    setSummaryTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...availableSummaryTypes.filter((x) => x === t || cur.includes(x))]));

  const run = async () => {
    if (s.import.status !== 'ready' || !s.sessionId || !window.mvr2t) return;
    try {
      const need = needsMindmapImage(items, summaryTypes.includes('mindmap'));
      let mindmapPng: string | undefined;
      let mindmapSvg: string | undefined;
      if (s.mindmap && (need.png || need.svg)) {
        setPhase({ kind: 'running', step: '正在產生心智圖圖片…' });
        const png = need.png ? await captureMindmap('png') : null;
        const svg = need.svg ? await captureMindmap('svg') : null;
        mindmapPng = png ? dataUrlPayload(png, 'png') : undefined;
        mindmapSvg = svg ? dataUrlPayload(svg, 'svg') : undefined;
      }
      setPhase({ kind: 'running', step: useFixed ? '正在匯出…' : '請選擇要存放的資料夾…' });
      const pending = window.mvr2t.exportFiles({
        sessionId: s.sessionId,
        mediaId: s.import.info.media_id,
        baseName: s.import.info.filename,
        items,
        mindmap: s.mindmap ? toSummary(s.mindmap) : undefined,
        mindmapPng,
        mindmapSvg,
        summaryTypes: exportsSummary && !allSummaryTypes ? summaryTypes : undefined,
        askFolder,
      });
      const res = await pending;
      if (!res.folder) {
        setPhase({ kind: 'choose' });
        return;
      }
      setPhase({ kind: 'done', folder: res.folder, results: res.results });
    } catch (err) {
      setPhase({ kind: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        if (running) e.preventDefault();
        else onClose();
      }}
      aria-labelledby="export-title"
      className="w-[min(720px,calc(100vw-32px))] rounded-xl bg-background p-0 text-foreground shadow-xl backdrop:bg-black/40"
    >
      <div className="flex max-h-[calc(100vh-64px)] flex-col">
        <div className="border-b border-chip px-6 py-5">
          <h2 id="export-title" className="text-h3">匯出</h2>
          <p className="mt-1 text-sm text-body-gray">
            勾選要匯出的內容與格式，接著選擇資料夾。檔名是「{s.import.status === 'ready' ? s.import.info.filename.replace(/\.[^.]+$/, '') : '檔名'}-內容.格式」，同名檔案不會被覆蓋。
          </p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {phase.kind === 'done' ? (
            <div className="flex flex-col gap-3" role="status">
              <div className="flex items-end gap-3">
                <Mono animation={phase.results.every((r) => r.ok) ? 'done' : 'error'} scale={1} />
                <p className="font-medium">
                  已匯出 {phase.results.filter((r) => r.ok).length} / {phase.results.length} 個檔案到
                  <span className="ml-1 break-all font-normal text-body-gray">{phase.folder}</span>
                </p>
              </div>
              <ul className="flex flex-col divide-y divide-chip rounded-lg border border-chip">
                {phase.results.map((r) => (
                  <li key={`${r.content}/${r.format}`} className="flex gap-3 px-4 py-2 text-sm">
                    <span aria-hidden className="w-4 font-bold">{r.ok ? '✓' : '✕'}</span>
                    {r.ok ? (
                      <span className="break-all">{fileName(r.path ?? '')}</span>
                    ) : (
                      <span>
                        {EXPORT_ROWS.find((x) => x.content === r.content)?.label} {FORMAT_LABELS[r.format]}：
                        <span className="text-body-gray">{r.error}</span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <fieldset disabled={running} className="flex flex-col [&>div+div]:border-t [&>div+div]:border-chip">
              <legend className="sr-only">匯出內容與格式</legend>
              {EXPORT_ROWS.map((row) => {
                const reason = unavailableReason(row.content, availability);
                const formats = EXPORT_FORMATS[row.content] as readonly ExportFormat[];
                return (
                  <div key={row.content} className={cn('flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:gap-4', reason && 'opacity-40')}>
                    <div className="sm:w-40 sm:shrink-0">
                      <p className="font-medium">{row.label}</p>
                      <p className="text-xs text-body-gray">
                        {reason ?? row.hint}
                        {!reason && row.content === 'segments_audio' && duration ? `（約 ${formatBytes(estimateZipBytes(duration))}）` : ''}
                      </p>
                    </div>
                    <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-2" role="group" aria-label={`${row.label}的格式`}>
                      {formats.map((f) => {
                        const on = !reason && !!sel[row.content]?.includes(f);
                        return (
                          <button
                            key={f}
                            type="button"
                            role="checkbox"
                            aria-checked={on}
                            disabled={!!reason}
                            onClick={() => update(toggleFormat(sel, row.content, f))}
                            className={cn(
                              'rounded-pill px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 disabled:cursor-not-allowed',
                              on ? 'bg-foreground text-background' : 'bg-chip hover:bg-hover-gray',
                            )}
                          >
                            {on ? '✓ ' : ''}
                            {FORMAT_LABELS[f]}
                          </button>
                        );
                      })}
                    </div>
                    {row.content === 'summary' && !reason && availableSummaryTypes.length > 1 ? (
                      <div className="flex flex-col gap-1.5">
                        <p className="text-xs text-body-gray">要匯出的摘要類型{noSummaryType ? <span className="ml-1 font-medium text-foreground">（至少勾選一種）</span> : null}</p>
                        <div className="flex flex-wrap gap-1.5" role="group" aria-label="要匯出的摘要類型">
                          {availableSummaryTypes.map((t) => {
                            const on = summaryTypes.includes(t);
                            return (
                              <button
                                key={t}
                                type="button"
                                role="checkbox"
                                aria-checked={on}
                                onClick={() => toggleSummaryType(t)}
                                className={cn(
                                  'rounded-pill border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground',
                                  on ? 'border-foreground bg-background' : 'border-hover-gray bg-background text-body-gray hover:border-foreground',
                                )}
                              >
                                {on ? '✓ ' : ''}
                                {SUMMARY_LABEL[t]}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                    </div>
                  </div>
                );
              })}
            </fieldset>
          )}
          {phase.kind === 'error' ? (
            <p role="alert" className="mt-3 rounded-lg bg-chip p-3 text-sm font-medium">匯出失敗：{phase.message}</p>
          ) : null}
          {!inElectron ? <p className="mt-3 text-sm text-body-gray">匯出需要在桌面程式中進行（瀏覽器預覽無法選擇資料夾）。</p> : null}
          {phase.kind !== 'done' && prefs ? (
            <div className="mt-3 rounded-lg bg-chip px-4 py-3 text-sm">
              {prefs.fixedFolder && prefs.fixedFolderAvailable ? (
                <>
                  <p>
                    {askFolder ? '這次會詢問存放的資料夾。' : '將存到設定中的資料夾：'}
                    {askFolder ? null : <span className="break-all text-body-gray">{prefs.fixedFolder}</span>}
                  </p>
                  <label className="mt-1 flex items-center gap-2 text-body-gray">
                    <input type="checkbox" checked={askFolder} onChange={(e) => setAskFolder(e.target.checked)} disabled={running} />
                    這次改選其他資料夾
                  </label>
                </>
              ) : prefs.fixedFolder ? (
                <p>設定中的資料夾目前找不到（<span className="break-all">{prefs.fixedFolder}</span>），這次會詢問存放位置。</p>
              ) : (
                <p className="text-body-gray">
                  按下匯出後選擇資料夾{prefs.lastFolder ? '（從上次的資料夾開始）' : ''}。可以在「設定」指定固定的匯出資料夾。
                </p>
              )}
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-chip px-6 py-4">
          {running ? (
            <span className="mr-auto text-sm text-body-gray" aria-live="polite">{phase.step}</span>
          ) : phase.kind === 'choose' || phase.kind === 'error' ? (
            <span className="mr-auto text-sm text-body-gray">{noSummaryType ? '摘要至少勾選一種類型' : `已選 ${items.length} 個檔案`}</span>
          ) : null}
          {phase.kind === 'done' ? (
            <>
              {window.mvr2t?.openExportFolder ? (
                <Button variant="ghost" className="mr-auto" onClick={() => void window.mvr2t?.openExportFolder()}>開啟資料夾</Button>
              ) : null}
              <Button variant="secondary" onClick={() => setPhase({ kind: 'choose' })}>再匯出其他</Button>
              <Button onClick={onClose}>完成</Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={onClose} disabled={running}>取消</Button>
              <Button onClick={() => void run()} disabled={running || items.length === 0 || noSummaryType || !inElectron}>
                {running ? '匯出中…' : `匯出 ${items.length} 個檔案`}
              </Button>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}
