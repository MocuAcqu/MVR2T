/** A sprite layer: rows of palette keys ('.' = transparent), placed at `at` = [x, y] on the canvas. */
export interface MonoPart {
  at: [number, number];
  rows: string[];
}

export type PaletteKey = 'K' | 'D' | 'G' | 'L' | 'W';

export interface MonoSprite {
  size: number;
  height: number;
  palette: Record<PaletteKey, string>;
  blob: MonoPart;
  feet: MonoPart;
  shadow: MonoPart;
  cheeks: MonoPart;
  tail: Record<MonoTail, MonoPart>;
  ears: Record<MonoEars, { back?: MonoPart; front?: MonoPart }>;
  eyes: Record<MonoEyes, MonoPart>;
  nose: Record<MonoNose, MonoPart>;
  hands: Record<MonoHands, MonoPart | null>;
  props: Record<MonoProp, MonoPart>;
}

export type MonoEars = 'up' | 'tilt' | 'sway' | 'fold' | 'down';
export type MonoEyes = 'open' | 'blink' | 'happy' | 'sleep' | 'wide' | 'down' | 'look' | 'x';
export type MonoNose = 'dot' | 'up' | 'sniff' | 'tiny';
export type MonoTail = 'rest' | 'up' | 'wag';
/** 'none' = just a mochi sitting on the ground (default); paws only appear while Mono is doing something. */
export type MonoHands = 'none' | 'rest' | 'wave' | 'cheer' | 'cover' | 'hold';
export type MonoProp = 'headphones' | 'notes1' | 'notes2' | 'tablet1' | 'tablet2';

/** One frame of Mono: every field is optional and falls back to the idle look. */
export interface MonoPose {
  ears?: MonoEars;
  eyes?: MonoEyes;
  nose?: MonoNose;
  tail?: MonoTail;
  hands?: MonoHands;
  /** Show the little feet even without paws (e.g. while hopping). Feet always show when paws do. */
  feet?: boolean;
  props?: MonoProp[];
}
