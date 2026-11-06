/** Supported import formats (PROJECT_SPEC 2.1-A). The backend must re-validate; never trust the client. */
export const VIDEO_EXTENSIONS = ['mp4', 'mov', 'mkv', 'webm'] as const;
export const AUDIO_EXTENSIONS = ['mp3', 'wav', 'm4a', 'flac', 'aac', 'ogg'] as const;
export const MEDIA_EXTENSIONS = [...VIDEO_EXTENSIONS, ...AUDIO_EXTENSIONS] as const;

export type MediaKind = 'video' | 'audio';

export function getExtension(filename: string): string {
  const i = filename.lastIndexOf('.');
  return i < 0 ? '' : filename.slice(i + 1).toLowerCase();
}

export function getMediaKind(filename: string): MediaKind | null {
  const ext = getExtension(filename);
  if ((VIDEO_EXTENSIONS as readonly string[]).includes(ext)) return 'video';
  if ((AUDIO_EXTENSIONS as readonly string[]).includes(ext)) return 'audio';
  return null;
}
