import { describe, expect, it } from 'vitest';
import { MEDIA_EXTENSIONS, getExtension, getMediaKind } from '@shared/constants/media';

describe('media formats (PROJECT_SPEC 2.1-A)', () => {
  it('covers exactly the formats in the spec', () => {
    expect([...MEDIA_EXTENSIONS].sort()).toEqual(
      ['aac', 'flac', 'm4a', 'mkv', 'mov', 'mp3', 'mp4', 'ogg', 'wav', 'webm'],
    );
  });

  it.each([
    ['lecture.mp4', 'video'],
    ['CLIP.MOV', 'video'],
    ['a.b.mkv', 'video'],
    ['x.webm', 'video'],
    ['talk.mp3', 'audio'],
    ['rec.WAV', 'audio'],
    ['voice.m4a', 'audio'],
    ['s.flac', 'audio'],
    ['s.aac', 'audio'],
    ['s.ogg', 'audio'],
  ])('%s is %s', (name, kind) => {
    expect(getMediaKind(name)).toBe(kind);
  });

  it.each(['notes.pdf', 'noextension', 'mp4', 'archive.mp4.zip', '.mp4x', ''])('%j is not media', (name) => {
    expect(getMediaKind(name)).toBeNull();
  });

  it('getExtension lowercases and handles missing dots', () => {
    expect(getExtension('A.MP4')).toBe('mp4');
    expect(getExtension('none')).toBe('');
    expect(getExtension('trailing.')).toBe('');
  });
});
