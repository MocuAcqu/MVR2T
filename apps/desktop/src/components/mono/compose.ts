import { MONO_SPRITE } from './sprite';
import type { MonoPart, MonoPose, MonoSprite, PaletteKey } from './types';

export interface MonoRect {
  x: number;
  y: number;
  w: number;
  fill: string;
}

/** Layer order, back to front. Held props (the tablet) go under the paws; worn props go on top. */
function layers(pose: MonoPose, s: MonoSprite): (MonoPart | null | undefined)[] {
  const ears = s.ears[pose.ears ?? 'up'];
  const hands = pose.hands ?? 'none';
  const props = pose.props ?? [];
  const held = props.filter((p) => p.startsWith('tablet'));
  const worn = props.filter((p) => !p.startsWith('tablet'));
  return [
    s.shadow,
    s.tail[pose.tail ?? 'rest'],
    ears.back,
    s.blob,
    pose.feet || hands !== 'none' ? s.feet : null,
    ears.front,
    s.cheeks,
    s.eyes[pose.eyes ?? 'open'],
    s.nose[pose.nose ?? 'dot'],
    ...held.map((p) => s.props[p]),
    s.hands[hands],
    ...worn.map((p) => s.props[p]),
  ];
}

/** Flatten a pose into a grid of palette keys ('.' = transparent). */
export function composeMono(pose: MonoPose = {}, s: MonoSprite = MONO_SPRITE): string[][] {
  const grid = Array.from({ length: s.height }, () => Array<string>(s.size).fill('.'));
  for (const part of layers(pose, s)) {
    if (!part) continue;
    const [ox, oy] = part.at;
    part.rows.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const c = row[x];
        const X = ox + x;
        const Y = oy + y;
        if (c !== '.' && X >= 0 && X < s.size && Y >= 0 && Y < s.height) grid[Y][X] = c;
      }
    });
  }
  return grid;
}

/** Horizontal runs of one color → few SVG rects per frame. */
export function monoRects(pose: MonoPose = {}, s: MonoSprite = MONO_SPRITE): MonoRect[] {
  const grid = composeMono(pose, s);
  const rects: MonoRect[] = [];
  grid.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const c = row[x];
      if (c === '.') {
        x++;
        continue;
      }
      let w = 1;
      while (x + w < row.length && row[x + w] === c) w++;
      rects.push({ x, y, w, fill: s.palette[c as PaletteKey] });
      x += w;
    }
  });
  return rects;
}
