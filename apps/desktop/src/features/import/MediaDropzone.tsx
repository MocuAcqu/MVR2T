import { FileAudio, FileVideo, Upload } from 'lucide-react';
import { useRef, useState, type DragEvent } from 'react';
import { AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS, getExtension, getMediaKind } from '@shared/constants/media';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cancelImport, importFile, removeMedia } from '@/features/media/mediaController';
import { formatBytes, formatDuration, formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useSessionStore, type ImportSource } from '@/stores/sessionStore';
import { Mono } from '@/components/mono/Mono';
import { GuideCoach } from '@/features/guide/GuideCoach';
import { GuideTarget } from '@/features/guide/GuideTarget';
import { t } from '@/i18n';

const ACCEPT = MEDIA_EXTENSIONS.map((e) => `.${e}`).join(',');
const list = (items: readonly string[]) => items.map((e) => e.toUpperCase()).join(t('、'));

function FileSummary({ file, duration }: { file: ImportSource; duration?: number }) {
  const kind = getMediaKind(file.name);
  const Icon = kind === 'audio' ? FileAudio : FileVideo;
  return (
    <div className="flex items-center gap-3 rounded-lg bg-chip p-4">
      <Icon className="size-6 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={file.name}>{file.name}</p>
        <p className="text-sm text-body-gray">{t('{0}，{1}，{2} {3}', kind === 'audio' ? t('音訊') : t('影片'), getExtension(file.name).toUpperCase(), formatBytes(file.size), duration !== undefined ? t('，長度 {0}', formatDuration(duration)) : '')}</p>
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
        <div className="flex items-end gap-4">
        <Mono animation={uploading ? 'loading' : 'video'} scale={2} />
        <div className="flex min-w-0 flex-1 flex-col gap-2" aria-live="polite">
          <div className="flex justify-between text-sm">
            <span className="font-medium">{uploading ? t('正在複製到工作階段') : t('正在檢查檔案')}</span>
            {uploading ? <span className="tabular-nums text-body-gray">{formatPercent(state.progress)}</span> : null}
          </div>
          <Progress
            label={uploading ? t('複製進度') : t('檢查檔案中')}
            value={uploading ? state.progress : undefined}
            indeterminate={!uploading}
          />
        </div>
        </div>
        <div>
          <Button variant="secondary" onClick={cancelImport}>{t('取消')}</Button>
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
          <GuideTarget step="open-workspace">
            <Button onClick={onOpenWorkspace}>{t('開啟工作區')}</Button>
          </GuideTarget>
          <Button variant="secondary" onClick={pick}>{t('更換檔案')}</Button>
          <Button variant="ghost" onClick={() => void removeMedia()}>{t('移除')}</Button>
        </div>
        <GuideCoach step="open-workspace" />
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
        <p className="text-lg font-medium">{dragging ? t('放開以匯入') : t('把影片或錄音拖到這裡')}</p>
        <Button onClick={pick}>{t('選擇檔案')}</Button>
        <p className="max-w-xs text-xs text-body-gray">{t('影片：{0}。音訊：{1}。', list(VIDEO_EXTENSIONS), list(AUDIO_EXTENSIONS))}</p>
      </div>
      {state.status === 'error' ? <p role="alert" className="text-sm font-medium">{state.message}</p> : null}
    </div>
  );
}
