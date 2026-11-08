import { FileAudio, FileVideo, Upload } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS, getExtension, getMediaKind } from '@shared/constants/media';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cancelImport, importFile, removeMedia } from '@/features/media/mediaController';
import { formatBytes, formatDuration, formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useSessionStore } from '@/stores/sessionStore';

const ACCEPT = MEDIA_EXTENSIONS.map((e) => `.${e}`).join(',');
const list = (items: readonly string[]) => items.map((e) => e.toUpperCase()).join('、');

function FileSummary({ file, duration }: { file: File; duration?: number }) {
  const kind = getMediaKind(file.name);
  const Icon = kind === 'audio' ? FileAudio : FileVideo;
  return (
    <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
      <Icon className="size-6 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={file.name}>{file.name}</p>
        <p className="text-sm text-body-gray">
          {kind === 'audio' ? '音訊' : '影片'}，{getExtension(file.name).toUpperCase()}，{formatBytes(file.size)}
          {duration !== undefined ? `，長度 ${formatDuration(duration)}` : ''}
        </p>
      </div>
    </div>
  );
}

/**
 * Drag-and-drop / file-picker import (Phase 04).
 * The file is copied into the backend session (with progress and cancel), then checked with ffprobe.
 */
export function MediaDropzone({ onOpenWorkspace }: { onOpenWorkspace: () => void }) {
  const state = useSessionStore((s) => s.import);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = (file?: File) => {
    if (file) void importFile(file);
  };
  const pick = () => inputRef.current?.click();

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

  if (state.status === 'uploading' || state.status === 'probing') {
    const uploading = state.status === 'uploading';
    return (
      <div className="flex flex-col gap-4">
        {hiddenInput}
        <FileSummary file={state.file} />
        <div className="flex flex-col gap-2" aria-live="polite">
          <div className="flex justify-between text-sm">
            <span className="font-medium">{uploading ? '正在複製到工作階段' : '正在檢查檔案'}</span>
            {uploading ? <span className="tabular-nums text-body-gray">{formatPercent(state.progress)}</span> : null}
          </div>
          <Progress
            label={uploading ? '複製進度' : '檢查檔案中'}
            value={uploading ? state.progress : undefined}
            indeterminate={!uploading}
          />
        </div>
        <div>
          <Button variant="secondary" onClick={cancelImport}>取消</Button>
        </div>
      </div>
    );
  }

  if (state.status === 'ready') {
    return (
      <div className="flex flex-col gap-4">
        {hiddenInput}
        <FileSummary file={state.file} duration={state.info.duration} />
        <div className="flex flex-wrap gap-2">
          <Button onClick={onOpenWorkspace}>開啟工作區</Button>
          <Button variant="secondary" onClick={pick}>更換檔案</Button>
          <Button variant="ghost" onClick={() => void removeMedia()}>移除</Button>
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
        <Button onClick={pick}>選擇檔案</Button>
        <p className="max-w-xs text-xs text-body-gray">
          影片：{list(VIDEO_EXTENSIONS)}。音訊：{list(AUDIO_EXTENSIONS)}。
        </p>
      </div>
      {state.status === 'error' ? <p role="alert" className="text-sm font-medium">{state.message}</p> : null}
    </div>
  );
}
