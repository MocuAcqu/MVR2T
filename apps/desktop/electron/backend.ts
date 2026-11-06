/**
 * Python Backend 行程管理（PROJECT_SPEC Phase 03 / §3.3 / §11）。
 *
 * 職責：
 * - 找到要執行的後端（開發：apps/backend/.venv 的 Python；正式版：Phase 11 的 PyInstaller 執行檔）。
 * - 以「參數陣列」spawn，不經過 shell（專案路徑含空格，且避免指令注入，規格 §11-10/11）。
 * - 讓作業系統挑選空閒連接埠，並產生一次性連線憑證。
 * - 等健康檢查通過才回報 running；逾時、找不到 Python、意外結束都轉成清楚的錯誤狀態。
 * - 結束時先關閉 stdin 讓後端優雅結束，逾時才強制終止。
 *   Electron 當機時 stdin 也會被作業系統關閉，後端同樣會自行結束（見 app/main.py 的 _watch_stdin）。
 *
 * 純函式（resolveBackendCommand、parseReadyLine…）與 BackendManager 都不直接依賴 Electron，方便用 vitest 測試。
 */
import { spawn as nodeSpawn, spawnSync, type ChildProcess, type SpawnOptions } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { BACKEND_READY_MARKER } from '@shared/constants/app';
import type { BackendState } from '@shared/types/ipc';

// ---------------------------------------------------------------------------
// 1. 找出要執行的後端指令
// ---------------------------------------------------------------------------

export interface BackendCommand {
  command: string;
  args: string[];
  cwd: string;
}

export type ResolveResult = { ok: true; cmd: BackendCommand } | { ok: false; message: string };

export interface ResolveOptions {
  platform: NodeJS.Platform;
  isPackaged: boolean;
  /** apps/backend 的絕對路徑（開發模式）。 */
  backendDir: string;
  /** Electron process.resourcesPath（正式版）。 */
  resourcesPath: string;
  /** 開發者可用 MVR2T_PYTHON 指定 Python 執行檔。 */
  pythonOverride?: string;
  exists?: (p: string) => boolean;
}

export function resolveBackendCommand(opts: ResolveOptions): ResolveResult {
  const exists = opts.exists ?? fs.existsSync;
  // 依目標平台選擇路徑規則，讓測試可以在任何作業系統驗證 Windows 路徑。
  const p = opts.platform === 'win32' ? path.win32 : path.posix;

  if (opts.isPackaged) {
    // Phase 11 / 12：PyInstaller onedir 輸出會放在 resources/backend/。
    const exe = p.join(opts.resourcesPath, 'backend', opts.platform === 'win32' ? 'mvr2t-backend.exe' : 'mvr2t-backend');
    if (!exists(exe)) return { ok: false, message: `安裝檔缺少後端程式：${exe}。請重新安裝 MVR2T。` };
    return { ok: true, cmd: { command: exe, args: [], cwd: p.dirname(exe) } };
  }

  const python =
    opts.pythonOverride ||
    (opts.platform === 'win32'
      ? p.join(opts.backendDir, '.venv', 'Scripts', 'python.exe')
      : p.join(opts.backendDir, '.venv', 'bin', 'python'));

  if (!exists(python)) {
    return {
      ok: false,
      message: `找不到後端的 Python：${python}。請依 README 在 apps/backend 建立 .venv（Python 3.11）並安裝 requirements/dev.txt。`,
    };
  }
  // `-m app.main`：Python 以 cwd 作為匯入根目錄，所以 cwd 必須是 apps/backend。
  return { ok: true, cmd: { command: python, args: ['-m', 'app.main'], cwd: opts.backendDir } };
}

// ---------------------------------------------------------------------------
// 2. 小工具
// ---------------------------------------------------------------------------

/** 解析後端輸出的「MVR2T_BACKEND_READY {"port":1234,"pid":5678}」。 */
export function parseReadyLine(line: string): { port: number; pid?: number } | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith(BACKEND_READY_MARKER)) return null;
  try {
    const data = JSON.parse(trimmed.slice(BACKEND_READY_MARKER.length).trim()) as { port?: unknown; pid?: unknown };
    const port = Number(data.port);
    if (!Number.isInteger(port) || port <= 0 || port > 65535) return null;
    return { port, pid: typeof data.pid === 'number' ? data.pid : undefined };
  } catch {
    return null;
  }
}

/** 256-bit 隨機憑證，每次啟動後端都重新產生。 */
export function createSessionToken(): string {
  return randomBytes(32).toString('base64url');
}

/** 子行程環境變數：繼承目前環境，再覆寫後端需要的設定。 */
export function buildBackendEnv(
  base: NodeJS.ProcessEnv,
  token: string,
  allowedOrigins: string[],
): NodeJS.ProcessEnv {
  return {
    ...base,
    MVR2T_BACKEND_PORT: '0', // 由作業系統挑選空閒埠
    MVR2T_AUTH_TOKEN: token,
    MVR2T_ALLOWED_ORIGINS: allowedOrigins.join(','),
    MVR2T_EXIT_ON_STDIN_EOF: '1',
    PYTHONUNBUFFERED: '1', // 立即輸出就緒訊息
    // 繁體中文 Windows 的預設編碼是 cp950；強制 UTF-8，避免輸出中文時崩潰。
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };
}

const LOG_TAIL_LINES = 40;

// ---------------------------------------------------------------------------
// 3. 行程管理
// ---------------------------------------------------------------------------

type SpawnFn = (command: string, args: string[], options: SpawnOptions) => ChildProcess;
type FetchFn = (url: string, init: { headers: Record<string, string>; signal: AbortSignal }) => Promise<{ ok: boolean }>;

export interface BackendManagerOptions {
  resolve: () => ResolveResult;
  allowedOrigins: string[];
  onState: (state: BackendState) => void;
  /** 將後端輸出轉給 Electron 主控台（開發時方便查看）。 */
  onLog?: (line: string) => void;
  startupTimeoutMs?: number;
  stopTimeoutMs?: number;
  spawn?: SpawnFn;
  fetch?: FetchFn;
  env?: NodeJS.ProcessEnv;
  /** 強制終止（預設 killProcessTree）；測試時可替換。 */
  killTree?: (child: ChildProcess) => void;
}

const initialState = (): BackendState => ({
  phase: 'stopped',
  url: null,
  token: null,
  pid: null,
  message: null,
  logTail: [],
  mode: 'managed',
});

export class BackendManager {
  private child: ChildProcess | null = null;
  private state: BackendState = initialState();
  /** 每次 start() 遞增；舊行程的事件一律忽略，避免 restart 時狀態錯亂。 */
  private generation = 0;
  private exitPromise: Promise<void> | null = null;
  private readonly opts: Required<Omit<BackendManagerOptions, 'onLog'>> & Pick<BackendManagerOptions, 'onLog'>;

  constructor(opts: BackendManagerOptions) {
    this.opts = {
      startupTimeoutMs: 30_000,
      stopTimeoutMs: 5_000,
      spawn: nodeSpawn,
      fetch: (url, init) => fetch(url, init),
      env: process.env,
      killTree: (child) => killProcessTree(child),
      ...opts,
    };
  }

  getState(): BackendState {
    return { ...this.state, logTail: [...this.state.logTail] };
  }

  private setState(patch: Partial<BackendState>): void {
    this.state = { ...this.state, ...patch };
    this.opts.onState(this.getState());
  }

  private appendLog(line: string): void {
    this.opts.onLog?.(line);
    this.state.logTail = [...this.state.logTail, line].slice(-LOG_TAIL_LINES);
  }

  /** 啟動後端；回傳時狀態為 running 或 error（不會丟出例外）。 */
  async start(): Promise<BackendState> {
    if (this.child) return this.getState();
    const gen = ++this.generation;
    const token = createSessionToken();
    this.state = { ...initialState(), phase: 'starting' };
    this.opts.onState(this.getState());

    const resolved = this.opts.resolve();
    if (!resolved.ok) {
      this.setState({ phase: 'error', message: resolved.message });
      return this.getState();
    }
    const { command, args, cwd } = resolved.cmd;

    let child: ChildProcess;
    try {
      // 參數陣列 + shell:false：路徑含空格也安全，且不會被當成 shell 指令解析。
      child = this.opts.spawn(command, args, {
        cwd,
        env: buildBackendEnv(this.opts.env, token, this.opts.allowedOrigins),
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: false,
        windowsHide: true,
      });
    } catch (err) {
      this.setState({ phase: 'error', message: `無法啟動後端：${(err as Error).message}` });
      return this.getState();
    }
    this.child = child;
    // 後端已結束時再關閉 stdin 會觸發 EPIPE；沒有監聽 'error' 會讓 Electron 主行程崩潰。
    child.stdin?.on('error', () => undefined);
    this.setState({ pid: child.pid ?? null });

    return new Promise<BackendState>((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(this.getState());
      };
      const timer = setTimeout(() => {
        if (gen !== this.generation || this.state.phase !== 'starting') return;
        this.setState({
          phase: 'error',
          message: `後端在 ${Math.round(this.opts.startupTimeoutMs / 1000)} 秒內沒有就緒。`,
        });
        void this.stop().then(finish);
      }, this.opts.startupTimeoutMs);

      this.exitPromise = new Promise<void>((resolveExit) => {
        // 'error'：例如執行檔不存在（ENOENT）或沒有執行權限。
        child.once('error', (err) => {
          if (gen !== this.generation) return;
          this.child = null;
          this.setState({ phase: 'error', pid: null, url: null, token: null, message: `無法啟動後端：${err.message}` });
          resolveExit();
          finish();
        });
        child.once('exit', (code, signal) => {
          if (gen !== this.generation) return resolveExit();
          this.child = null;
          const wasStopping = this.state.phase === 'stopping';
          if (wasStopping) {
            this.setState({ phase: 'stopped', pid: null, url: null, token: null });
          } else if (this.state.phase !== 'error') {
            this.setState({
              phase: 'error',
              pid: null,
              url: null,
              token: null,
              message: `後端意外結束（${signal ? `訊號 ${signal}` : `代碼 ${code ?? '未知'}`}）。`,
            });
          }
          resolveExit();
          finish();
        });
      });

      const onLine = (line: string) => {
        if (gen !== this.generation) return;
        this.appendLog(line);
        const ready = parseReadyLine(line);
        if (ready && this.state.phase === 'starting') {
          void this.waitForHealth(gen, `http://127.0.0.1:${ready.port}`, token).then((ok) => {
            if (ok) {
              // Windows venv 的 python.exe 是啟動器；ready 行回報的才是實際伺服器 PID。
              this.setState({ phase: 'running', url: `http://127.0.0.1:${ready.port}`, token, pid: ready.pid ?? this.state.pid });
              finish();
            }
          });
        }
      };
      pipeLines(child.stdout, onLine);
      pipeLines(child.stderr, onLine);
    });
  }

  /** 輪詢健康檢查直到成功、行程結束或被新的 start() 取代。 */
  private async waitForHealth(gen: number, url: string, token: string): Promise<boolean> {
    while (gen === this.generation && this.state.phase === 'starting') {
      try {
        const res = await this.opts.fetch(`${url}/api/health`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(1500),
        });
        if (res.ok) return gen === this.generation && this.state.phase === 'starting';
      } catch {
        // 還沒開始監聽；稍後重試
      }
      await delay(150);
    }
    return false;
  }

  /** 優雅結束：關閉 stdin → 等待 → 逾時強制終止。重複呼叫是安全的。 */
  async stop(): Promise<void> {
    const child = this.child;
    if (!child) {
      if (this.state.phase === 'starting' || this.state.phase === 'running') this.setState({ phase: 'stopped' });
      return;
    }
    if (this.state.phase !== 'error') this.setState({ phase: 'stopping' });
    const exited = this.exitPromise ?? Promise.resolve();

    child.stdin?.end(); // 後端讀到 EOF 後自行結束
    const graceful = await Promise.race([exited.then(() => true), delay(this.opts.stopTimeoutMs).then(() => false)]);
    if (!graceful && this.child === child) {
      this.appendLog('[electron] backend did not exit in time; killing');
      this.opts.killTree(child);
      await Promise.race([exited, delay(2_000)]);
    }
  }

  async restart(): Promise<BackendState> {
    await this.stop();
    return this.start();
  }

  /** 最後防線：主行程即將結束且來不及等待時同步終止子行程。 */
  killNow(): void {
    if (this.child) this.opts.killTree(this.child);
  }
}

function pipeLines(stream: NodeJS.ReadableStream | null | undefined, onLine: (line: string) => void): void {
  if (!stream) return;
  stream.setEncoding('utf8');
  let buffer = '';
  stream.on('data', (chunk: string) => {
    buffer += chunk;
    let i: number;
    while ((i = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, i).replace(/\r$/, '');
      buffer = buffer.slice(i + 1);
      if (line) onLine(line);
    }
  });
  stream.on('end', () => {
    if (buffer.trim()) onLine(buffer.trim());
    buffer = '';
  });
}

/**
 * 強制終止後端「整個行程樹」。
 * Windows 的 .venv\Scripts\python.exe 只是啟動器，真正的伺服器是它的子行程；
 * 只 kill 啟動器可能留下孤兒，所以 Windows 用 `taskkill /T /F`（同步，可在 process 'exit' 中使用）。
 */
export function killProcessTree(child: ChildProcess, platform: NodeJS.Platform = process.platform): void {
  if (child.exitCode !== null || child.pid === undefined) return;
  if (platform === 'win32') {
    const r = spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    if (r.status === 0) return;
  }
  child.kill('SIGKILL');
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
