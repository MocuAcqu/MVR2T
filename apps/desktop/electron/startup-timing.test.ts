import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { formatStartupLine, StartupTimer, trimLines } from './startup-timing';

describe('startup timing log', () => {
  it('formats marks in a fixed order and skips missing ones', () => {
    const line = formatStartupLine(new Date('2026-11-15T00:00:00Z'), true, { 'window-shown': 900, 'app-ready': 300, 'backend-running': 5000 });
    expect(line).toBe('2026-11-15T00:00:00.000Z packaged=true app-ready=300 backend-running=5000 window-shown=900');
  });

  it('keeps only the most recent lines', () => {
    const text = Array.from({ length: 60 }, (_, i) => `line ${i}`).join('\n') + '\n';
    const out = trimLines(text, 50).trimEnd().split('\n');
    expect(out).toHaveLength(50);
    expect(out[0]).toBe('line 10');
  });

  it('writes one line once the window is shown and the backend is running', async () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'mvr2t-startup-'));
    const file = path.join(dir, 'logs', 'startup.log');
    writeFileSync(path.join(dir, 'unused'), '');
    let t = 0;
    const timer = new StartupTimer(() => file, false, () => (t += 100));
    timer.mark('app-ready');
    timer.mark('backend-spawned');
    timer.mark('window-shown');
    timer.mark('backend-running');
    await timer.write(); // already written by mark(); a second write is a no-op
    timer.mark('backend-running');
    const lines = readFileSync(file, 'utf-8').trim().split('\n');
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatch(/packaged=false app-ready=100 backend-spawned=200 backend-running=400 window-shown=300$/);
  });
});
