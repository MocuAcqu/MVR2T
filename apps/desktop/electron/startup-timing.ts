/**
 * 啟動時間記錄（Phase 11 fix1）：正式版從點捷徑到首頁約 18 秒，先量測各階段再決定怎麼改善。
 * 每次啟動在 userData/logs/startup.log 加一行（只保留最近 MAX_LINES 行），例如：
 *   2026-11-15T10:00:00.000Z packaged=true app-ready=820 window-shown=2400 backend-spawned=830 backend-ready-line=9100 backend-running=9600
 * 數字是主行程啟動後的毫秒數（process.uptime）。
 */
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

export const MAX_LINES = 50;
export const STARTUP_MARKS = ['app-ready', 'backend-spawned', 'backend-ready-line', 'backend-running', 'window-shown'] as const;
export type StartupMark = (typeof STARTUP_MARKS)[number];

export function formatStartupLine(at: Date, packaged: boolean, marks: Partial<Record<StartupMark, number>>): string {
  const parts = STARTUP_MARKS.filter((m) => marks[m] !== undefined).map((m) => `${m}=${marks[m]}`);
  return `${at.toISOString()} packaged=${packaged} ${parts.join(' ')}`;
}

export function trimLines(text: string, max = MAX_LINES): string {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '');
  return lines.slice(-max).join('\n') + (lines.length ? '\n' : '');
}

export class StartupTimer {
  private readonly marks: Partial<Record<StartupMark, number>> = {};
  private writing: Promise<void> | null = null;

  constructor(
    private readonly logFile: () => string,
    private readonly packaged: boolean,
    private readonly now: () => number = () => Math.round(process.uptime() * 1000),
  ) {}

  mark(name: StartupMark): void {
    if (this.marks[name] !== undefined || this.writing) return;
    this.marks[name] = this.now();
    console.log(`[startup] ${name} +${this.marks[name]} ms`);
    if (this.marks['window-shown'] !== undefined && this.marks['backend-running'] !== undefined) void this.write();
  }

  /** 視窗顯示且後端就緒後寫一次；寫入失敗不影響程式。 */
  write(): Promise<void> {
    this.writing ??= this.doWrite();
    return this.writing;
  }

  private async doWrite(): Promise<void> {
    const file = this.logFile();
    try {
      await mkdir(path.dirname(file), { recursive: true });
      await appendFile(file, formatStartupLine(new Date(), this.packaged, this.marks) + '\n', 'utf-8');
      const text = await readFile(file, 'utf-8');
      const trimmed = trimLines(text);
      if (trimmed !== text) await writeFile(file, trimmed, 'utf-8');
    } catch (e) {
      console.log(`[startup] could not write ${file}: ${String(e)}`);
    }
  }
}
