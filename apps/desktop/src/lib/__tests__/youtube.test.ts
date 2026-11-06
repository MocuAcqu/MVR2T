import { describe, expect, it } from 'vitest';
import { parseYouTubeUrl } from '@/lib/youtube';

const ID = 'dQw4w9WgXcQ';

describe('parseYouTubeUrl', () => {
  it.each([
    `https://www.youtube.com/watch?v=${ID}`,
    `https://youtube.com/watch?v=${ID}&t=42s`,
    `https://m.youtube.com/watch?v=${ID}`,
    `https://music.youtube.com/watch?v=${ID}`,
    `https://youtu.be/${ID}`,
    `https://youtu.be/${ID}?si=abc`,
    `https://www.youtube.com/shorts/${ID}`,
    `https://www.youtube.com/embed/${ID}`,
    `https://www.youtube.com/live/${ID}`,
    `www.youtube.com/watch?v=${ID}`, // no scheme
    `  https://youtu.be/${ID}  `, // surrounding whitespace
  ])('accepts %s', (url) => {
    expect(parseYouTubeUrl(url)).toBe(ID);
  });

  it.each([
    '',
    '   ',
    'hello world',
    'https://example.com/watch?v=dQw4w9WgXcQ',
    'https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com/watch?v=short',
    'https://www.youtube.com/watch',
    'https://www.youtube.com/channel/UC123',
    'https://youtu.be/',
    'javascript:alert(1)',
  ])('rejects %j', (url) => {
    expect(parseYouTubeUrl(url)).toBeNull();
  });
});
