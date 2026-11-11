import { useState, type ReactNode } from 'react';
import type { Summary, SummaryType, TimeSpan } from '@shared/types/api';
import { Mono } from '@/components/mono/Mono';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { GuideCoach } from '@/features/guide/GuideCoach';
import { GuideTarget } from '@/features/guide/GuideTarget';
import { useExportUi } from '@/features/export/exportStore';
import { KeepAwakeNote } from '@/features/media/KeepAwakeNote';
import { cancelSummary, startSummary } from '@/features/media/mediaController';
import { revealTranscriptLine } from '@/features/workspace/TranscriptCard';
import { formatDuration, formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/sessionStore';

export const SUMMARY_TYPES: { value: SummaryType; label: string; hint: string }[] = [
  { value: 'overview', label: '全文摘要', hint: '一段話說明內容與結論' },
  { value: 'key_points', label: '重點整理', hint: '5～10 個重點，附時間' },
  { value: 'notes', label: '條列式筆記', hint: '分小節的條列筆記' },
  { value: 'topics', label: '主題分類', hint: '歸納出幾個主題' },
  { value: 'keywords', label: '關鍵字', hint: '人名、地名、專有名詞' },
  { value: 'action_items', label: '行動事項', hint: '誰要做什麼、期限' },
  { value: 'qa', label: '問題與結論', hint: '討論的問題與結論' },
  { value: 'mindmap', label: '心智圖', hint: '從中心主題向左右展開，顯示在下方，可以編輯與匯出' },
];
const LABEL = Object.fromEntries(SUMMARY_TYPES.map((t) => [t.value, t.label])) as Record<SummaryType, string>;
const DEFAULT_TYPES: SummaryType[] = ['overview', 'key_points', 'keywords', 'action_items', 'mindmap'];
/** 心智圖顯示在自己的卡片（MindMapCard），不在摘要分頁中 */
const tabTypes = (summary: Summary) => summary.types.filter((t) => t !== 'mindmap');

/** 時間標籤：點一下捲動到逐字稿中對應的句子。 */
function TimeChip({ time, refs }: { time: TimeSpan | null; refs: number[] }) {
  if (!time || refs.length === 0) return null;
  return (
    <button
      type="button"
      onClick={() => revealTranscriptLine(refs[0])}
      title="跳到逐字稿中的這一句"
      className="ml-2 inline-flex shrink-0 items-center rounded-pill bg-chip px-2 py-0.5 align-middle text-xs tabular-nums text-body-gray hover:bg-hover-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground"
    >
      {formatDuration(Math.floor(time.start))}
    </button>
  );
}

function Empty() {
  return <p className="text-sm text-body-gray">內容中沒有找到這一類的項目。</p>;
}

function SummaryBody({ summary, type }: { summary: Summary; type: SummaryType }) {
  const r = summary.results;
  let body: ReactNode = null;
  switch (type) {
    case 'overview':
      body = r.overview ? <p className="whitespace-pre-line leading-relaxed">{r.overview}</p> : <Empty />;
      break;
    case 'key_points':
      body = r.key_points?.length ? (
        <ol className="flex list-decimal flex-col gap-2 pl-5">
          {r.key_points.map((p, i) => (
            <li key={i} className="leading-relaxed">
              {p.text}
              <TimeChip time={p.time} refs={p.refs} />
            </li>
          ))}
        </ol>
      ) : (
        <Empty />
      );
      break;
    case 'notes':
      body = r.notes?.length ? (
        <div className="flex flex-col gap-4">
          {r.notes.map((s, i) => (
            <section key={i}>
              <h4 className="font-bold">
                {s.title}
                <TimeChip time={s.time} refs={s.refs} />
              </h4>
              <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
                {s.bullets.map((b, j) => (
                  <li key={j} className="leading-relaxed">{b}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <Empty />
      );
      break;
    case 'topics':
      body = r.topics?.length ? (
        <ul className="grid gap-3 sm:grid-cols-2">
          {r.topics.map((t, i) => (
            <li key={i} className="rounded-lg bg-chip p-4">
              <p className="font-bold">
                {t.title}
                <TimeChip time={t.time} refs={t.refs} />
              </p>
              <p className="mt-1 text-sm text-body-gray">{t.description}</p>
            </li>
          ))}
        </ul>
      ) : (
        <Empty />
      );
      break;
    case 'keywords':
      body = r.keywords?.length ? (
        <ul className="flex flex-wrap gap-2">
          {r.keywords.map((k) => (
            <li key={k}>
              <Badge>{k}</Badge>
            </li>
          ))}
        </ul>
      ) : (
        <Empty />
      );
      break;
    case 'action_items':
      body = r.action_items?.length ? (
        <ul className="flex flex-col divide-y divide-chip rounded-lg border border-chip">
          {r.action_items.map((a, i) => (
            <li key={i} className="flex flex-col gap-1 px-4 py-3">
              <p className="leading-relaxed">
                {a.task}
                <TimeChip time={a.time} refs={a.refs} />
              </p>
              <p className="text-sm text-body-gray">
                負責：{a.owner || '未指定'}　期限：{a.due || '未提到'}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <Empty />
      );
      break;
    case 'qa':
      body = r.qa?.length ? (
        <dl className="flex flex-col gap-3">
          {r.qa.map((q, i) => (
            <div key={i}>
              <dt className="font-bold">
                {q.question}
                <TimeChip time={q.time} refs={q.refs} />
              </dt>
              <dd className="mt-1 leading-relaxed text-body-gray">{q.conclusion}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <Empty />
      );
      break;
  }
  return <div role="tabpanel" aria-label={LABEL[type]}>{body}</div>;
}

/** 摘要：勾選要產生的內容 → 本機 LLM（llama.cpp）產生，長逐字稿分段後階層式整合（PROJECT_SPEC Phase 06）。 */
export function SummaryCard() {
  const transcript = useSessionStore((s) => s.transcript);
  const s = useSessionStore((st) => st.summarizing);
  const summary = useSessionStore((st) => st.summary);
  const [types, setTypes] = useState<SummaryType[]>(DEFAULT_TYPES);
  const [tab, setTab] = useState<SummaryType | null>(null);

  const ready = !!transcript && transcript.segments.length > 0;
  const busy = s.status === 'starting' || s.status === 'queued' || s.status === 'running';
  const loadingModel = busy && (s.status === 'starting' || s.stage.includes('載入'));
  const tabs: SummaryType[] = summary ? tabTypes(summary) : [];
  const activeTab = tab && tabs.includes(tab) ? tab : (tabs[0] ?? null);

  const toggle = (t: SummaryType) => setTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  return (
    <Card>
      <CardHeader>
        <CardTitle>摘要</CardTitle>
        <CardDescription>在這台電腦上以本機語言模型整理逐字稿；只根據逐字稿內容，不會上傳，也不需要網路。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!ready ? <p className="text-sm text-body-gray">請先完成「語音辨識」，再產生摘要。</p> : null}

        <fieldset disabled={!ready || busy} className="disabled:opacity-40">
          <legend className="mb-2 text-sm font-medium">要產生的內容</legend>
          <div className="flex flex-wrap gap-2">
            {SUMMARY_TYPES.map((t) => {
              const on = types.includes(t.value);
              return (
                <button
                  key={t.value}
                  type="button"
                  role="checkbox"
                  aria-checked={on}
                  title={t.hint}
                  onClick={() => toggle(t.value)}
                  className={cn(
                    'rounded-pill px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2',
                    on ? 'bg-foreground text-background' : 'bg-chip hover:bg-hover-gray',
                  )}
                >
                  {on ? '✓ ' : ''}
                  {t.label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-body-gray">勾選越多，需要的時間越長（每一種約需 1～3 分鐘，依電腦效能而定）。</p>
        </fieldset>

        {busy ? (
          <div className="flex items-end gap-4">
            {/* 載入模型時原地跳；整理時捧著小螢幕讀逐字稿 */}
            <Mono animation={loadingModel ? 'loading' : 'video'} scale={2} />
            <div className="flex min-w-0 flex-1 flex-col gap-2" aria-live="polite">
              <div className="flex justify-between gap-4 text-sm">
                <span className="font-medium">
                  {s.stage || '準備中'}
                  {s.detail ? <span className="ml-2 font-normal text-body-gray">{s.detail}</span> : null}
                </span>
                {loadingModel ? null : <span className="tabular-nums text-body-gray">{formatPercent(s.progress)}</span>}
              </div>
              <Progress label="摘要進度" value={s.progress} indeterminate={loadingModel} />
              <p className="text-xs text-body-gray">
                {loadingModel
                  ? '正在把摘要模型載入記憶體（約 2.5 GB），第一次需要一些時間。'
                  : '長錄音會先分段閱讀，再整合成完整的摘要。完成時如果你正在用其他程式，會跳出系統通知。'}
              </p>
              <KeepAwakeNote />
            </div>
          </div>
        ) : null}

        {s.status === 'failed' ? (
          <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
            <Mono animation="error" scale={1} />
            <p role="alert" className="text-sm font-medium">{s.message ?? '摘要失敗。'}</p>
          </div>
        ) : null}
        {s.status === 'cancelled' ? <p role="status" className="text-sm text-body-gray">已取消產生摘要。</p> : null}

        {summary && activeTab ? (
          <div className="flex flex-col gap-4">
            <div role="tablist" aria-label="摘要內容" className="flex flex-wrap gap-2">
              {tabs.map((t) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={t === activeTab}
                  onClick={() => setTab(t)}
                  className={cn(
                    'rounded-pill px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2',
                    t === activeTab ? 'bg-foreground text-background' : 'bg-chip hover:bg-hover-gray',
                  )}
                >
                  {LABEL[t]}
                </button>
              ))}
            </div>
            <SummaryBody summary={summary} type={activeTab} />
            <p className="text-xs text-body-gray">
              由本機模型產生，可能有錯誤或遺漏，重要內容請對照逐字稿確認。
              {summary.chunks > 1 ? `逐字稿分成 ${summary.chunks} 段閱讀後整合。` : ''}處理 {formatDuration(summary.elapsed_seconds)}。
            </p>
          </div>
        ) : null}

        <GuideCoach step="summarize" />
        <GuideCoach step="done" />
      </CardContent>
      <CardFooter className="flex-wrap">
        {busy ? (
          <Button variant="secondary" onClick={() => void cancelSummary()} disabled={s.status === 'starting'}>
            取消
          </Button>
        ) : (
          <GuideTarget step="summarize">
            <Button onClick={() => void startSummary(types)} disabled={!ready || types.length === 0}>
              {s.status === 'completed' ? '重新產生摘要' : s.status === 'idle' ? '產生摘要' : '再試一次'}
            </Button>
          </GuideTarget>
        )}
        {summary && !busy ? (
          <Button variant="secondary" className="ml-auto" onClick={() => useExportUi.getState().openPanel(['summary'])}>
            匯出
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  );
}
