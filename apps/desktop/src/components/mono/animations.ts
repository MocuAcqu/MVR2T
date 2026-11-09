import type { MonoPose } from './types';

/** Whole-body motion (CSS, squash & stretch from the bottom like a mochi). Defined in index.css. */
export type MonoMotion = 'breathe' | 'bounce' | 'sway' | 'none';

export interface MonoAnimation {
  /** [pose, duration in ms]; loops. */
  frames: [MonoPose, number][];
  motion: MonoMotion;
}

const music = ['headphones', 'notes1'] as MonoPose['props'];
const music2 = ['headphones', 'notes2'] as MonoPose['props'];

export const MONO_ANIMATIONS = {
  /** Sitting around: blinks, nose twitches, tail wags, looks around. */
  idle: {
    motion: 'breathe',
    frames: [
      [{}, 2000],
      [{ eyes: 'blink' }, 140],
      [{}, 900],
      [{ nose: 'up' }, 120],
      [{}, 120],
      [{ nose: 'up' }, 120],
      [{}, 1200],
      [{ tail: 'wag' }, 160],
      [{}, 160],
      [{ tail: 'wag' }, 160],
      [{}, 1200],
      [{ ears: 'tilt', eyes: 'look' }, 900],
      [{}, 500],
      [{ eyes: 'blink' }, 140],
    ],
  },
  /** Generic waiting: hops in place, feet show while hopping. */
  loading: {
    motion: 'bounce',
    frames: [
      [{ eyes: 'happy', nose: 'up', tail: 'up', feet: true }, 450],
      [{ feet: true }, 450],
    ],
  },
  /** Audio work (extracting / cutting): headphones on, long ears sway to the beat, notes float up. */
  music: {
    motion: 'breathe',
    frames: [
      [{ ears: 'sway', eyes: 'sleep', props: music }, 420],
      [{ ears: 'tilt', eyes: 'sleep', nose: 'up', props: music2 }, 420],
    ],
  },
  /** Video / transcription work: holds a little screen that flickers; sniffs at the exciting parts. */
  video: {
    motion: 'breathe',
    frames: [
      [{ eyes: 'down', hands: 'hold', props: ['tablet1'] }, 300],
      [{ eyes: 'down', hands: 'hold', props: ['tablet2'] }, 300],
      [{ eyes: 'down', hands: 'hold', nose: 'up', props: ['tablet1'] }, 300],
      [{ eyes: 'blink', hands: 'hold', props: ['tablet2'] }, 140],
      [{ eyes: 'wide', hands: 'hold', nose: 'sniff', props: ['tablet1'] }, 600],
    ],
  },
  /** Explaining the next step: body sways left and right while the nose twitches. */
  hint: {
    motion: 'sway',
    frames: [
      [{ nose: 'up' }, 160],
      [{}, 160],
      [{ nose: 'up' }, 160],
      [{}, 900],
      [{ eyes: 'blink' }, 140],
    ],
  },
  /** Finished: cheers with both paws up, tail up. */
  done: {
    motion: 'bounce',
    frames: [
      [{ eyes: 'happy', hands: 'cheer', tail: 'up' }, 450],
      [{ eyes: 'happy', hands: 'cheer', tail: 'wag' }, 450],
    ],
  },
  /** Something went wrong: long ears droop, X eyes. */
  error: {
    motion: 'none',
    frames: [
      [{ ears: 'down', eyes: 'x', nose: 'tiny' }, 1800],
      [{ ears: 'down', eyes: 'blink', nose: 'tiny' }, 160],
    ],
  },
} satisfies Record<string, MonoAnimation>;

export type MonoAnimationName = keyof typeof MONO_ANIMATIONS;

/** Mouse over an interactive Mono: it gets curious and sniffs at the pointer. */
export const MONO_CURIOUS: MonoAnimation = {
  motion: 'breathe',
  frames: [
    [{ ears: 'fold', eyes: 'wide', nose: 'sniff' }, 180],
    [{ ears: 'fold', eyes: 'wide', nose: 'up' }, 180],
  ],
};

/** Clicked: a happy squish. */
export const MONO_POKED: MonoPose = { eyes: 'happy', hands: 'cheer', tail: 'up' };
