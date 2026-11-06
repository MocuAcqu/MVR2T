import { describe, expect, it } from 'vitest';
import { formatBytes } from '@/lib/format';

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [1024, '1.0 KB'],
    [1536, '1.5 KB'],
    [150 * 1024, '150 KB'],
    [5 * 1024 ** 2, '5.0 MB'],
    [2.5 * 1024 ** 3, '2.5 GB'],
    [3 * 1024 ** 4, '3.0 TB'],
    [2048 * 1024 ** 4, '2048 TB'], // stays in the largest unit
  ])('%d -> %s', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  it.each([-1, NaN, Infinity])('invalid %d -> "-"', (bytes) => {
    expect(formatBytes(bytes)).toBe('-');
  });
});
