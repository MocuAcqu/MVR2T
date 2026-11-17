import { Combine, Play, Trash2, Undo2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Transcript, TranscriptSegment } from '@shared/types/api';
import { Button } from '@/components/ui/button';
import { seekTo, usePlayerStore } from '@/features/player/playerStore';
import { formatTimestamp } from '@/lib/format';
import { deleteSegment, editText, mergeWithNext, saveSegments } from './transcriptEdit';
import { t } from '@/i18n';

const SAVE_DELAY_MS = 700;
const MAX_UNDO = 50;
type SaveState = { status: 'idle' | 'saving' | 'saved' } | { status: 'error'; message: string };

/** 依內容自動調整高度的文字框 */
function AutoTextarea({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      aria-label={label}
      rows={1}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full resize-none overflow-hidden rounded-md border border-chip bg-background px-2 py-1 leading-relaxed focus-visible:border-foreground focus-visible:outline-none"
    />
  );
}

/**
 * 逐字稿編輯器（規格 §2.1-D）：編輯文字、刪除、與下一句合併、復原。修改會自動儲存（只存在本次工作階段）；
 * 之後的匯出、摘要都使用編輯後的內容。
 */
export function TranscriptEditor({ transcript, onDone }: { transcript: Transcript; onDone: () => void }) {
  const [draft, setDraft] = useState<TranscriptSegment[]>(transcript.segments);
  const [history, setHistory] = useState<TranscriptSegment[][]>([]);
  const [save, setSave] = useState<SaveState>({ status: 'idle' });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<TranscriptSegment[] | null>(null);
  const playerReady = usePlayerStore((s) => s.ready);

  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const segments = pending.current;
    pending.current = null;
    if (!segments) return true;
    setSave({ status: 'saving' });
    try {
      await saveSegments(segments);
      setSave({ status: 'saved' });
      return true;
    } catch (err) {
      setSave({ status: 'error', message: err instanceof Error ? err.message : String(err) });
      pending.current = segments; // 下一次修改或按「完成」時再試
      return false;
    }
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      if (pending.current) void flush();
    },
    [flush],
  );

  /** 套用一個修改：記錄復原點，存檔（文字輸入延遲，其他立即）。 */
  const apply = (next: TranscriptSegment[], delay: boolean, record = true) => {
    if (record) setHistory((h) => [...h.slice(-(MAX_UNDO - 1)), draft]);
    setDraft(next);
    pending.current = next;
    if (timer.current) clearTimeout(timer.current);
    if (delay) timer.current = setTimeout(() => void flush(), SAVE_DELAY_MS);
    else void flush();
  };

  // 連續輸入只記一個復原點：開始輸入一句時記錄一次
  const typing = useRef<number | null>(null);
  const onText = (id: number, text: string) => {
    const first = typing.current !== id;
    typing.current = id;
    apply(editText(draft, id, text), true, first);
  };
  const structural = (next: TranscriptSegment[]) => {
    typing.current = null;
    apply(next, false);
  };
  const undo = () => {
    const prev = history[history.length - 1];
    if (!prev) return;
    typing.current = null;
    setHistory((h) => h.slice(0, -1));
    apply(prev, false, false);
  };

  const status =
    save.status === 'saving' ? t('儲存中…') : save.status === 'saved' ? t('已儲存') : save.status === 'error' ? t('儲存失敗：{0}', save.message) : t('修改會自動儲存');

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" size="sm" onClick={undo} disabled={history.length === 0}>
          <Undo2 className="size-4" aria-hidden="true" />
          {t('復原')}
        </Button>
        <span role="status" className={save.status === 'error' ? 'text-sm font-medium' : 'text-sm text-body-gray'}>
          {status}
        </span>
        <Button
          size="sm"
          className="ml-auto"
          onClick={() => {
            void flush().then((ok) => {
              if (ok) onDone();
            });
          }}
        >
          {t('完成編輯')}
        </Button>
      </div>
      <p className="text-xs text-body-gray">
        {t('直接修改文字；把一句的文字全部刪掉等於刪除這一句。時間戳記不會改變；合併時開始時間取第一句、結束時間取第二句。')}
      </p>
      <ol className="max-h-[40rem] overflow-auto rounded-lg border border-chip" aria-label={t('編輯逐字稿')}>
        {draft.map((s, i) => (
          <li key={s.id} className="flex gap-3 border-t border-chip px-3 py-2 first:border-t-0">
            <div className="flex w-24 shrink-0 flex-col gap-1 pt-1">
              <span className="text-xs tabular-nums text-body-gray">{formatTimestamp(s.start)}</span>
              <button
                type="button"
                className="flex items-center gap-1 self-start rounded-pill px-1.5 py-0.5 text-xs hover:bg-chip disabled:opacity-40"
                onClick={() => seekTo(s.start)}
                disabled={!playerReady}
                title={t('從這一句開始播放')}
              >
                <Play className="size-3" aria-hidden="true" />
                {t('播放')}
              </button>
            </div>
            <div className="min-w-0 flex-1">
              <AutoTextarea value={s.text} onChange={(v) => onText(s.id, v)} label={t('第 {0} 句', i + 1)} />
            </div>
            <div className="flex shrink-0 flex-col gap-1">
              <button
                type="button"
                className="flex items-center gap-1 rounded-pill px-2 py-1 text-xs hover:bg-chip disabled:opacity-40"
                onClick={() => structural(mergeWithNext(draft, s.id))}
                disabled={i === draft.length - 1}
                title={t('把下一句接在這一句後面')}
              >
                <Combine className="size-3.5" aria-hidden="true" />
                {t('與下一句合併')}
              </button>
              <button
                type="button"
                className="flex items-center gap-1 rounded-pill px-2 py-1 text-xs hover:bg-chip"
                onClick={() => structural(deleteSegment(draft, s.id))}
                title={t('刪除這一句')}
              >
                <Trash2 className="size-3.5" aria-hidden="true" />
                {t('刪除')}
              </button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
