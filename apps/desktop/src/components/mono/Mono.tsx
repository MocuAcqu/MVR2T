import { useEffect, useMemo, useState } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { cn } from '@/lib/utils';
import { MONO_ANIMATIONS, MONO_CURIOUS, MONO_POKED, type MonoAnimation, type MonoAnimationName } from './animations';
import { monoRects } from './compose';
import { MONO_SPRITE } from './sprite';
import type { MonoPose } from './types';

const MOTION_CLASS = { breathe: 'mono-breathe', bounce: 'mono-bounce', sway: 'mono-sway', none: '' } as const;

/** Loops through an animation's frames. With reduced motion it stays on the first frame. */
function useFrame(anim: MonoAnimation, paused: boolean): MonoPose {
  const [i, setI] = useState(0);
  useEffect(() => setI(0), [anim]);
  useEffect(() => {
    if (paused || anim.frames.length < 2) return;
    const t = window.setTimeout(() => setI((n) => (n + 1) % anim.frames.length), anim.frames[i % anim.frames.length][1]);
    return () => window.clearTimeout(t);
  }, [anim, i, paused]);
  return anim.frames[i % anim.frames.length][0];
}

export interface MonoProps {
  /** Named animation (default: idle). Ignored when `pose` is given. */
  animation?: MonoAnimationName;
  /** A fixed pose instead of an animation. */
  pose?: MonoPose;
  /** Screen pixels per sprite pixel (the sprite is 32×36). */
  scale?: number;
  /** Reacts to the mouse: curious on hover, a happy squish on click. */
  interactive?: boolean;
  /** Accessible description. Without it Mono is decorative and hidden from screen readers. */
  label?: string;
  className?: string;
}

/** Mono, MVR2T's pixel mascot: a white mochi rabbit. Sprite parts are composed per frame and drawn as crisp SVG rects. */
export function Mono({ animation = 'idle', pose, scale = 3, interactive = false, label, className }: MonoProps) {
  const reduced = usePrefersReducedMotion();
  const [hover, setHover] = useState(false);
  const [poked, setPoked] = useState(false);

  useEffect(() => {
    if (!poked) return;
    const t = window.setTimeout(() => setPoked(false), 700);
    return () => window.clearTimeout(t);
  }, [poked]);

  const curious = interactive && hover;
  const stableAnim = useMemo<MonoAnimation>(
    () => (pose ? { frames: [[pose, 1000]], motion: 'none' } : curious ? MONO_CURIOUS : MONO_ANIMATIONS[animation]),
    [pose, curious, animation],
  );
  const frame = useFrame(stableAnim, reduced);
  const shown = poked ? MONO_POKED : frame;
  const rects = useMemo(() => monoRects(shown), [shown]);

  const { size: w, height: h } = MONO_SPRITE;
  const motion = reduced ? '' : poked ? 'mono-jelly' : MOTION_CLASS[stableAnim.motion];

  const svg = (
    <svg
      width={w * scale}
      height={h * scale}
      viewBox={`0 0 ${w} ${h}`}
      shapeRendering="crispEdges"
      className={cn('block', motion)}
      // A labelled, non-interactive Mono is an image; inside the button the button carries the label.
      role={label && !interactive ? 'img' : undefined}
      aria-label={label && !interactive ? label : undefined}
      aria-hidden={label && !interactive ? undefined : true}
    >
      {rects.map((r) => (
        <rect key={`${r.x},${r.y}`} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />
      ))}
    </svg>
  );

  if (!interactive) return <span className={cn('inline-block shrink-0', className)}>{svg}</span>;
  return (
    <button
      type="button"
      aria-label={label ?? 'Mono'}
      title="Mono"
      className={cn(
        'inline-block shrink-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2',
        className,
      )}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      onClick={() => setPoked(true)}
    >
      {svg}
    </button>
  );
}
