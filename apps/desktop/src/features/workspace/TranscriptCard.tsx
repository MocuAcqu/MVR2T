import { useId, useState } from 'react';
import type { AsrLanguage, Transcript } from '@shared/types/api';
import { Mono } from '@/components/mono/Mono';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { KeepAwakeNote } from '@/features/media/KeepAwakeNote';
import { cancelTranscription, startTranscription } from '@/features/media/mediaController';
import { GuideCoach } from '@/features/guide/GuideCoach';
import { GuideTarget } from '@/features/guide/GuideTarget';
import { formatDuration, formatPercent, formatTimestamp } from '@/lib/format';
import { useSessionStore } from '@/stores/sessionStore';

const LANGUAGES: { value: AsrLanguage | 'auto'; label: string }[] = [
  { value: 'auto', label: '自動偵測' },
  { value: 'Chinese', label: '中文' },
  { value: 'English', label: '英文' },
  { value: 'Cantonese', label: '粵語' },
  { value: 'Japanese', label: '日文' },
  { value: 'Korean', label: '韓文' },
];

const LANGUAGE_LABEL: Record<string, string> = Object.fromEntries(
  LANGUAGES.filter((l) => l.value !== 'auto').map((l) => [l.value, l.label]),
);

export const languageLabel = (lang: string | null) => (lang ? (LANGUAGE_LABEL[lang] ?? lang) : '未知');

const TIMING_LABEL: Record<Transcript['timing'], string> = {
  aligned: '精確時間',
  estimated: '估計時間',
  mixed: '部分估計',
};

/** 逐字稿句子的 DOM id：摘要的時間點會捲動到這裡（見 SummaryCard）。 */
export const transcriptLineId = (id: number) => `transcript-line-${id}`;

/** 捲動到逐字稿中的某一句並短暫標示。 */
export function revealTranscriptLine(id: number): void {
  const el = document.getElementById(transcriptLineId(id));
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('bg-chip');
  window.setTimeout(() => el.classList.remove('bg-chip'), 1800);
}

function TranscriptList({ transcript }: { transcript: Transcript }) {
  return (
    <ol className="max-h-[32rem] overflow-auto rounded-lg border border-chip" aria-label="逐字稿">
      {transcript.segments.map((s) => (
        <li
          key={s.id}
          id={transcriptLineId(s.id)}
          className="flex scroll-mt-4 gap-4 border-t border-chip px-4 py-3 transition-colors first:border-t-0"
        >
          <span
            className="w-28 shrink-0 pt-0.5 text-xs tabular-nums text-body-gray"
            title={s.timing === 'estimated' ? '依字數估計的時間' : `${formatTimestamp(s.start)} → ${formatTimestamp(s.end)}`}
          >
            {formatTimestamp(s.start)}
            {s.timing === 'estimated' ? ' *' : ''}
          </span>
          <p className="min-w-0 flex-1 leading-relaxed">{s.text}</p>
        </li>
      ))}
    </ol>
  );
}

/** 語音辨識：Qwen3-ASR 逐段辨識 → 對齊模型產生時間戳記（PROJECT_SPEC Phase 05）。 */
export function TranscriptCard() {
  const selectId = useId();
  const extraction = useSessionStore((s) => s.extraction);
  const t = useSessionStore((s) => s.transcription);
  const transcript = useSessionStore((s) => s.transcript);
  const [language, setLanguage] = useState<AsrLanguage | 'auto'>('auto');

  const ready = extraction.status === 'completed';
  const busy = t.status === 'starting' || t.status === 'queued' || t.status === 'running';
  // 載入模型時無法估計進度（首次從磁碟讀取 1.5～1.8 GB，Windows 實測約 80 秒）→ 顯示不確定進度
  const loadingModel = busy && (t.status === 'starting' || t.stage.includes('載入'));
  const result = t.result;
  const estimatedCount = transcript ? transcript.segments.filter((s) => s.timing === 'estimated').length : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>逐字稿</CardTitle>
        <CardDescription>
          在這台電腦上以 Qwen3-ASR 辨識語音，並以對齊模型產生每句的時間戳記。中文會自動轉為繁體（台灣用語）。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!ready && !transcript ? <p className="text-sm text-body-gray">請先完成「抽取音訊」，再開始語音辨識。</p> : null}

        {busy ? (
          <div className="flex items-end gap-4">
          {/* 載入模型時原地跳著等；辨識時捧著小螢幕看 */}
          <Mono animation={loadingModel ? 'loading' : 'video'} scale={2} />
          <div className="flex min-w-0 flex-1 flex-col gap-2" aria-live="polite">
            <div className="flex justify-between gap-4 text-sm">
              <span className="font-medium">
                {t.stage || '準備中'}
                {t.detail ? <span className="ml-2 font-normal text-body-gray">{t.detail}</span> : null}
              </span>
              {loadingModel ? null : <span className="tabular-nums text-body-gray">{formatPercent(t.progress)}</span>}
            </div>
            <Progress label="語音辨識進度" value={t.progress} indeterminate={loadingModel} />
            <p className="text-xs text-body-gray">
              {loadingModel
                ? '正在把模型載入記憶體。第一次約需 1～2 分鐘，之後會比較快。'
                : '處理時間依電腦效能而定，長錄音可能需要與錄音長度相近的時間。完成時如果你正在用其他程式，會跳出系統通知。'}
            </p>
            <KeepAwakeNote />
          </div>
          </div>
        ) : null}

        {t.status === 'completed' && result && transcript ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm" role="status">
              <Badge variant="solid">{languageLabel(transcript.language)}</Badge>
              <Badge variant={transcript.timing === 'aligned' ? 'default' : 'outline'}>{TIMING_LABEL[transcript.timing]}</Badge>
              <span className="text-body-gray">
                {transcript.segments.length} 句，音訊 {formatDuration(result.audio_seconds)}，處理 {formatDuration(result.elapsed_seconds)}
                {result.timings?.asr_seconds !== undefined
                  ? `（辨識 ${formatDuration(result.timings.asr_seconds)}${
                      result.timings.align_seconds !== undefined ? `、對齊 ${formatDuration(result.timings.align_seconds)}` : ''
                    }）`
                  : ''}
              </span>
            </div>
            {transcript.warnings.length > 0 ? (
              <ul className="list-inside list-disc rounded-lg bg-chip p-4 text-sm">
                {transcript.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            ) : null}
            {transcript.segments.length > 0 ? (
              <TranscriptList transcript={transcript} />
            ) : (
              <p className="text-sm text-body-gray">沒有辨識到語音內容。</p>
            )}
            {estimatedCount > 0 ? (
              <p className="text-xs text-body-gray">
                {transcript.timing === 'mixed'
                  ? `其中 ${estimatedCount} 句（標 *）的時間是依字數估計，通常是極短的語助詞或對齊模型無法對應的句子；其餘為精確時間。`
                  : '* 為依字數估計的時間。'}
              </p>
            ) : null}
          </>
        ) : null}

        {t.status === 'failed' ? (
          <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
            <Mono animation="error" scale={1} />
            <p role="alert" className="text-sm font-medium">{t.message ?? '語音辨識失敗。'}</p>
          </div>
        ) : null}
        {t.status === 'cancelled' ? <p role="status" className="text-sm text-body-gray">已取消語音辨識。</p> : null}
        <GuideCoach step="transcribe" />
      </CardContent>
      <CardFooter className="flex-wrap">
        {busy ? (
          <Button variant="secondary" onClick={() => void cancelTranscription()} disabled={t.status === 'starting'}>
            取消
          </Button>
        ) : (
          <>
            <label htmlFor={selectId} className="sr-only">辨識語言</label>
            <select
              id={selectId}
              value={language}
              onChange={(e) => setLanguage(e.target.value as AsrLanguage | 'auto')}
              disabled={!ready}
              className="h-11 rounded-pill border border-foreground bg-background px-4 text-base font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 disabled:opacity-40"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </select>
            <GuideTarget step="transcribe">
              <Button onClick={() => void startTranscription(language === 'auto' ? null : language)} disabled={!ready}>
                {t.status === 'completed' ? '重新辨識' : t.status === 'idle' ? '開始語音辨識' : '再試一次'}
              </Button>
            </GuideTarget>
          </>
        )}
      </CardFooter>
    </Card>
  );
}
