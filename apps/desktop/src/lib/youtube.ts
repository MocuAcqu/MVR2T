const YOUTUBE_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be']);
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;

/** Returns the video ID for a valid YouTube URL, otherwise null. Format check only (no network). */
export function parseYouTubeUrl(input: string): string | null {
  const text = input.trim();
  if (!text) return null;
  let url: URL;
  try {
    url = new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`);
  } catch {
    return null;
  }
  const host = url.hostname.toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) return null;

  let id: string | null = null;
  if (host === 'youtu.be') id = url.pathname.split('/')[1] ?? null;
  else if (url.pathname === '/watch') id = url.searchParams.get('v');
  else id = /^\/(?:shorts|embed|live)\/([^/?#]+)/.exec(url.pathname)?.[1] ?? null;

  return id && VIDEO_ID.test(id) ? id : null;
}
