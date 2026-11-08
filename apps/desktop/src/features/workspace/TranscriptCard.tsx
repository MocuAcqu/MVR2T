import { useId, useState } from 'react';
import type { AsrLanguage, Transcript } from '@shared/types/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cancelTranscription, startTranscription } from '@/features/media/mediaController';
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

function TranscriptList({ transcript }: { transcript: Transcript }) {
  return (
    <ol className="max-h-[32rem] overflow-auto rounded-lg border border-chip" aria-label="逐字稿">
      {transcript.segments.map((s) => (
        <li key={s.id} className="flex gap-4 border-t border-chip px-4 py-3 first:border-t-0">
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
  const result = t.result;

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
          <div className="flex flex-col gap-2" aria-live="polite">
            <div className="flex justify-between gap-4 text-sm">
              <span className="font-medium">
                {t.stage || '準備中'}
                {t.detail ? <span className="ml-2 font-normal text-body-gray">{t.detail}</span> : null}
              </span>
              <span className="tabular-nums text-body-gray">{formatPercent(t.progress)}</span>
            </div>
            <Progress label="語音辨識進度" value={t.progress} />
            <p className="text-xs text-body-gray">處理時間依電腦效能而定；首次載入模型需要數秒。</p>
          </div>
        ) : null}

        {t.status === 'completed' && result && transcript ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm" role="status">
              <Badge variant="solid">{languageLabel(transcript.language)}</Badge>
              <Badge variant={transcript.timing === 'aligned' ? 'default' : 'outline'}>{TIMING_LABEL[transcript.timing]}</Badge>
              <span className="text-body-gray">
                {transcript.segments.length} 句，音訊 {formatDuration(result.audio_seconds)}，處理 {formatDuration(result.elapsed_seconds)}
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
            {transcript.timing !== 'aligned' ? <p className="text-xs text-body-gray">* 為依字數估計的時間。</p> : null}
          </>
        ) : null}

        {t.status === 'failed' ? (
          <p role="alert" className="rounded-lg bg-chip p-4 text-sm font-medium">{t.message ?? '語音辨識失敗。'}</p>
        ) : null}
        {t.status === 'cancelled' ? <p role="status" className="text-sm text-body-gray">已取消語音辨識。</p> : null}
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
            <Button onClick={() => void startTranscription(language === 'auto' ? null : language)} disabled={!ready}>
              {t.status === 'completed' ? '重新辨識' : t.status === 'idle' ? '開始語音辨識' : '再試一次'}
            </Button>
          </>
        )}
      </CardFooter>
    </Card>
  );
}
