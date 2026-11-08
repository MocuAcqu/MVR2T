import { describe, expect, it } from 'vitest';
import { formatBytes, formatDuration, formatPercent, formatTimestamp } from '@/lib/format';

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

describe('formatDuration', () => {
  it.each([
    [0, '0:00'],
    [5.4, '0:05'],
    [59.6, '1:00'],
    [125, '2:05'],
    [3723, '1:02:03'],
    [36000, '10:00:00'],
  ])('%d -> %s', (s, expected) => {
    expect(formatDuration(s)).toBe(expected);
  });
  it.each([-1, NaN, Infinity])('invalid %d -> "-"', (s) => {
    expect(formatDuration(s)).toBe('-');
  });
});

describe('formatTimestamp', () => {
  it.each([
    [0, '00:00:00.000'],
    [31.25, '00:00:31.250'],
    [62.001, '00:01:02.001'],
    [3723.5, '01:02:03.500'],
  ])('%d -> %s', (s, expected) => {
    expect(formatTimestamp(s)).toBe(expected);
  });
});

describe('formatPercent', () => {
  it.each([
    [0, '0%'],
    [0.425, '42%'],
    [0.999, '99%'], // never shows 100% before it is really done
    [1, '100%'],
    [1.5, '100%'],
    [-0.2, '0%'],
    [NaN, '0%'],
  ])('%d -> %s', (f, expected) => {
    expect(formatPercent(f)).toBe(expected);
  });
});
