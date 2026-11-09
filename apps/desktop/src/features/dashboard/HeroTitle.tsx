import { useEffect, useState } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

const WORDS = ['Media', 'Video', 'Record'] as const;

/** 固定的「音波」高度（不用亂數，每次畫面一樣）。 */
const BARS = Array.from({ length: 40 }, (_, i) => 10 + Math.round(46 * Math.abs(Math.sin(i * 0.55) * Math.cos(i * 0.21))));

/** 首頁大標題：Your [Media → Video → Record] 輪播＋像素音波。螢幕閱讀器讀到的是完整、不變的標題。 */
export function HeroTitle() {
  const reduced = usePrefersReducedMotion();
  const [i, setI] = useState(0);
  const [lift, setLift] = useState(false);

  useEffect(() => {
    if (reduced) return;
    const id = window.setInterval(() => {
      setLift(true);
      window.setTimeout(() => {
        setI((n) => (n + 1) % WORDS.length);
        setLift(false);
      }, 150);
    }, 2200);
    return () => window.clearInterval(id);
  }, [reduced]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-h1 tracking-tight xl:text-display" aria-label="Your Media. Your Video. Your Record.">
        {reduced ? (
          <span aria-hidden>
            Your Media.
            <br />
            Your Video.
            <br />
            Your Record.
          </span>
        ) : (
          <span aria-hidden className="whitespace-nowrap">
            Your{' '}
            <span
              className="inline-block min-w-[5.2ch] rounded-lg bg-foreground px-3 text-center text-background transition-transform duration-150"
              style={{ transform: lift ? 'translateY(-6px)' : undefined }}
            >
              {WORDS[i]}
            </span>
          </span>
        )}
      </h1>
      <p className="text-lg text-body-gray">把影片與錄音轉成逐字稿、摘要和心智圖</p>
      <div aria-hidden className="mt-2 flex h-14 items-end gap-1">
        {BARS.map((h, k) => (
          <i
            key={k}
            className="block w-2 origin-bottom animate-wave bg-foreground"
            style={{ height: `${h}px`, animationDelay: `${((k * 7) % 9) * 0.1}s` }}
          />
        ))}
      </div>
    </div>
  );
}
