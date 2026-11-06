import { FileAudio, FileVideo, Upload } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS, getExtension, getMediaKind } from '@shared/constants/media';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/sessionStore';

const ACCEPT = MEDIA_EXTENSIONS.map((e) => `.${e}`).join(',');
const list = (items: readonly string[]) => items.map((e) => e.toUpperCase()).join('、');

/** Drag-and-drop / file-picker import. Format check only; the backend re-validates in Phase 04. */
export function MediaDropzone({ onOpenWorkspace }: { onOpenWorkspace: () => void }) {
  const media = useSessionStore((s) => s.media);
  const setMedia = useSessionStore((s) => s.setMedia);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = (file?: File) => {
    if (!file) return;
    if (!getMediaKind(file.name)) {
      setError(`不支援這個檔案格式。請選擇 ${list(MEDIA_EXTENSIONS)} 其中一種。`);
      return;
    }
    setError(null);
    setMedia(file);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    accept(e.dataTransfer.files[0]);
  };

  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      accept={ACCEPT}
      tabIndex={-1}
      aria-hidden="true"
      className="sr-only"
      onChange={(e) => {
        accept(e.target.files?.[0]);
        e.target.value = ''; // allow choosing the same file again
      }}
    />
  );

  if (media) {
    const kind = getMediaKind(media.name);
    const Icon = kind === 'audio' ? FileAudio : FileVideo;
    return (
      <div className="flex flex-col gap-4">
        {hiddenInput}
        <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
          <Icon className="size-6 shrink-0" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium" title={media.name}>{media.name}</p>
            <p className="text-sm text-body-gray">
              {kind === 'audio' ? '音訊' : '影片'}，{getExtension(media.name).toUpperCase()}，{formatBytes(media.size)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onOpenWorkspace}>開啟工作區</Button>
          <Button variant="secondary" onClick={() => inputRef.current?.click()}>更換檔案</Button>
          <Button variant="ghost" onClick={() => setMedia(null)}>移除</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {hiddenInput}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={onDrop}
        className={cn(
          'flex flex-col items-center gap-3 rounded-lg border border-dashed border-foreground px-4 py-8 text-center transition-colors',
          dragging ? 'border-solid bg-chip' : 'bg-background',
        )}
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-chip">
          <Upload className="size-5" aria-hidden="true" />
        </span>
        <p className="text-lg font-medium">{dragging ? '放開以匯入' : '把影片或錄音拖到這裡'}</p>
        <Button onClick={() => inputRef.current?.click()}>選擇檔案</Button>
        <p className="max-w-xs text-xs text-body-gray">
          影片：{list(VIDEO_EXTENSIONS)}。音訊：{list(AUDIO_EXTENSIONS)}。
        </p>
      </div>
      {error ? <p role="alert" className="text-sm font-medium">{error}</p> : null}
    </div>
  );
}
