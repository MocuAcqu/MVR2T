import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { parseYouTubeUrl } from '@/lib/youtube';

type Result = { ok: true; id: string } | { ok: false; message: string } | null;

/** Validates the URL format only. Embed preview and subtitle retrieval need the network (later release). */
export function YouTubeUrlInput() {
  const inputId = useId();
  const messageId = useId();
  const [url, setUrl] = useState('');
  const [result, setResult] = useState<Result>(null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return setResult({ ok: false, message: '請輸入 YouTube 網址。' });
    const id = parseYouTubeUrl(url);
    setResult(id ? { ok: true, id } : { ok: false, message: '這不是有效的 YouTube 影片網址。' });
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2" noValidate>
      <label htmlFor={inputId} className="text-sm font-medium">YouTube 網址</label>
      <div className="flex gap-2">
        <Input
          id={inputId}
          type="url"
          inputMode="url"
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => { setUrl(e.target.value); setResult(null); }}
          aria-invalid={result?.ok === false}
          aria-describedby={result ? messageId : undefined}
        />
        <Button type="submit" variant="secondary" className="shrink-0">檢查網址</Button>
      </div>
      {result ? (
        <p id={messageId} role={result.ok ? 'status' : 'alert'} className="flex items-start gap-2 text-sm">
          {result.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
          <span>
            {result.ok
              ? '網址格式正確。影片預覽與官方字幕需要網路，將在後續版本提供；目前請匯入本機檔案。'
              : result.message}
          </span>
        </p>
      ) : null}
    </form>
  );
}
