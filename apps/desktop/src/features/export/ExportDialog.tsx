import { useEffect, useRef, useState } from 'react';
import { EXPORT_FORMATS } from '@shared/constants/app';
import type { ExportFormat, ExportItemResult } from '@shared/types/ipc';
import { Mono } from '@/components/mono/Mono';
import { Button } from '@/components/ui/button';
import { captureMindmap } from '@/features/mindmap/capture';
import { dataUrlPayload } from '@/features/mindmap/exportImage';
import { toSummary } from '@/features/mindmap/model';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/sessionStore';
import {
  DEFAULT_SELECTION,
  EXPORT_ROWS,
  FORMAT_LABELS,
  estimateZipBytes,
  needsMindmapImage,
  selectedItems,
  toggleFormat,
  unavailableReason,
  type Availability,
  type Selection,
} from './exportPlan';

// 勾選只記在這次開啟的程式中（不寫入任何儲存空間）
let rememberedSelection: Selection = DEFAULT_SELECTION;

type Phase = { kind: 'choose' } | { kind: 'running'; step: string } | { kind: 'done'; folder: string; results: ExportItemResult[] } | { kind: 'error'; message: string };

const fileName = (p: string) => p.split(/[\\/]/).pop() ?? p;

/** 工作區的「匯出」面板（Phase 08）：勾選內容與格式 → 選資料夾 → 一次寫入。 */
export function ExportDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const s = useSessionStore();
  const [sel, setSel] = useState<Selection>(rememberedSelection);
  const [phase, setPhase] = useState<Phase>({ kind: 'choose' });

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setPhase({ kind: 'choose' });
      d.showModal();
    } else if (!open && d.open) d.close();
  }, [open]);

  const availability: Availability = {
    segments: s.extraction.status === 'completed' && !!s.extraction.result,
    transcript: !!s.transcript && s.transcript.segments.length > 0,
    summary: !!s.summary,
    mindmap: !!s.mindmap,
  };
  const items = selectedItems(sel, availability);
  const inElectron = !!window.mvr2t?.exportFiles;
  const running = phase.kind === 'running';
  const duration = s.import.status === 'ready' ? s.import.info.duration : 0;

  const update = (next: Selection) => {
    rememberedSelection = next;
    setSel(next);
  };

  const run = async () => {
    if (s.import.status !== 'ready' || !s.sessionId || !window.mvr2t) return;
    try {
      const need = needsMindmapImage(items);
      let mindmapPng: string | undefined;
      let mindmapSvg: string | undefined;
      if (s.mindmap && (need.png || need.svg)) {
        setPhase({ kind: 'running', step: '正在產生心智圖圖片…' });
        const png = need.png ? await captureMindmap('png') : null;
        const svg = need.svg ? await captureMindmap('svg') : null;
        mindmapPng = png ? dataUrlPayload(png, 'png') : undefined;
        mindmapSvg = svg ? dataUrlPayload(svg, 'svg') : undefined;
      }
      setPhase({ kind: 'running', step: '請選擇要存放的資料夾…' });
      const pending = window.mvr2t.exportFiles({
        sessionId: s.sessionId,
        mediaId: s.import.info.media_id,
        baseName: s.import.info.filename,
        items,
        mindmap: s.mindmap ? toSummary(s.mindmap) : undefined,
        mindmapPng,
        mindmapSvg,
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
                  </div>
                );
              })}
            </fieldset>
          )}
          {phase.kind === 'error' ? (
            <p role="alert" className="mt-3 rounded-lg bg-chip p-3 text-sm font-medium">匯出失敗：{phase.message}</p>
          ) : null}
          {!inElectron ? <p className="mt-3 text-sm text-body-gray">匯出需要在桌面程式中進行（瀏覽器預覽無法選擇資料夾）。</p> : null}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-chip px-6 py-4">
          {running ? (
            <span className="mr-auto text-sm text-body-gray" aria-live="polite">{phase.step}</span>
          ) : phase.kind === 'choose' || phase.kind === 'error' ? (
            <span className="mr-auto text-sm text-body-gray">已選 {items.length} 個檔案</span>
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
              <Button onClick={() => void run()} disabled={running || items.length === 0 || !inElectron}>
                {running ? '匯出中…' : `匯出 ${items.length} 個檔案`}
              </Button>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}
