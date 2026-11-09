import { describe, expect, it } from 'vitest';
import { MONO_ANIMATIONS } from '../animations';
import { composeMono, monoRects } from '../compose';
import { MONO_SPRITE } from '../sprite';

const count = (g: string[][], c: string) => g.flat().filter((x) => x === c).length;

describe('Mono sprite', () => {
  it('every part fits on the canvas', () => {
    const parts = [
      MONO_SPRITE.blob, MONO_SPRITE.feet, MONO_SPRITE.shadow, MONO_SPRITE.cheeks,
      ...Object.values(MONO_SPRITE.tail), ...Object.values(MONO_SPRITE.eyes), ...Object.values(MONO_SPRITE.nose),
      ...Object.values(MONO_SPRITE.props), ...Object.values(MONO_SPRITE.hands),
      ...Object.values(MONO_SPRITE.ears).flatMap((e) => [e.back, e.front]),
    ];
    for (const p of parts) {
      if (!p) continue;
      const [x, y] = p.at;
      expect(x).toBeGreaterThanOrEqual(0);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y + p.rows.length).toBeLessThanOrEqual(MONO_SPRITE.height);
      for (const r of p.rows) expect(x + r.length).toBeLessThanOrEqual(MONO_SPRITE.size);
    }
  });

  it('is a plain mochi by default: no paws or feet until Mono does something', () => {
    const plain = composeMono({});
    const withFeet = composeMono({ feet: true });
    const waving = composeMono({ hands: 'wave' });
    expect(count(withFeet, 'W')).toBeGreaterThan(count(plain, 'W'));
    expect(JSON.stringify(waving)).not.toBe(JSON.stringify(plain));
    // feet rows sit below the blob: row 34+ only has the ground shadow when idle
    expect(plain[35].every((c) => c === '.')).toBe(true);
    expect(withFeet[34].some((c) => c === 'K' || c === 'W')).toBe(true);
  });

  it('the face is symmetric when idle', () => {
    const g = composeMono({});
    for (let y = 18; y < 25; y++) {
      const row = g[y].slice(5, 27).map((c) => (c === 'L' ? 'W' : c)).join('');
      expect(row).toBe([...row].reverse().join(''));
    }
  });

  it('only uses the gray palette', () => {
    const colors = new Set(Object.values(MONO_ANIMATIONS).flatMap((a) => a.frames.flatMap(([p]) => monoRects(p).map((r) => r.fill))));
    for (const c of colors) expect(Object.values(MONO_SPRITE.palette)).toContain(c);
  });
});
