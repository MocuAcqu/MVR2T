import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Sizes stored in an .ico file (0 in the directory entry means 256). */
function icoSizes(file: string): number[] {
  const buf = readFileSync(file);
  expect(buf.readUInt16LE(2)).toBe(1); // type 1 = icon
  const n = buf.readUInt16LE(4);
  return Array.from({ length: n }, (_, i) => buf[6 + i * 16] || 256);
}

describe('app icon (scripts/generate_icons.py)', () => {
  it('window icon has every Windows size, small ones hand-drawn', () => {
    expect(icoSizes(join(__dirname, '../build/icon.ico'))).toEqual([16, 32, 48, 256]);
  });
  it('favicon has the small sizes', () => {
    expect(icoSizes(join(__dirname, '../public/favicon.ico'))).toEqual([16, 32, 48]);
  });
  it('png icon for macOS/Linux is 512 px', () => {
    const png = readFileSync(join(__dirname, '../build/icon.png'));
    expect(png.readUInt32BE(16)).toBe(512);
    expect(png.readUInt32BE(20)).toBe(512);
  });
});
