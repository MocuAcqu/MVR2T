import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { ChildProcess } from 'node:child_process';
import { describe, expect, it, vi } from 'vitest';
import type { BackendState } from '@shared/types/ipc';
import {
  BackendManager,
  buildBackendEnv,
  createSessionToken,
  parseReadyLine,
  resolveBackendCommand,
  type ResolveResult,
} from './backend';

describe('resolveBackendCommand', () => {
  const winDir = 'C:\\Users\\User\\Desktop\\MVR2T AI\\apps\\backend';

  it('uses the Windows venv python and keeps the path with spaces as ONE argument', () => {
    const r = resolveBackendCommand({
      platform: 'win32', isPackaged: false, backendDir: winDir, resourcesPath: '', exists: () => true,
    });
    expect(r).toEqual({
      ok: true,
      cmd: { command: `${winDir}\\.venv\\Scripts\\python.exe`, args: ['-m', 'app.main'], cwd: winDir },
    });
  });

  it('uses .venv/bin/python on macOS', () => {
    const r = resolveBackendCommand({
      platform: 'darwin', isPackaged: false, backendDir: '/Users/me/MVR2T AI/apps/backend', resourcesPath: '', exists: () => true,
    });
    expect(r.ok && r.cmd.command).toBe('/Users/me/MVR2T AI/apps/backend/.venv/bin/python');
  });

  it('honours MVR2T_PYTHON override', () => {
    const r = resolveBackendCommand({
      platform: 'win32', isPackaged: false, backendDir: winDir, resourcesPath: '', pythonOverride: 'D:\\py\\python.exe', exists: () => true,
    });
    expect(r.ok && r.cmd.command).toBe('D:\\py\\python.exe');
  });

  it('returns a readable error when the venv is missing', () => {
    const r = resolveBackendCommand({
      platform: 'win32', isPackaged: false, backendDir: winDir, resourcesPath: '', exists: () => false,
    });
    expect(r.ok).toBe(false);
    expect(!r.ok && r.message).toContain('.venv');
  });

  it('uses the PyInstaller executable when packaged (Phase 11)', () => {
    const r = resolveBackendCommand({
      platform: 'win32', isPackaged: true, backendDir: '', resourcesPath: 'C:\\Program Files\\MVR2T\\resources', exists: () => true,
    });
    expect(r.ok && r.cmd).toEqual({
      command: 'C:\\Program Files\\MVR2T\\resources\\backend\\mvr2t-backend.exe',
      args: [],
      cwd: 'C:\\Program Files\\MVR2T\\resources\\backend',
    });
  });
});

describe('parseReadyLine', () => {
  it('parses the marker line', () => {
    expect(parseReadyLine('MVR2T_BACKEND_READY {"port": 51234, "pid": 99}')).toEqual({ port: 51234, pid: 99 });
    expect(parseReadyLine('MVR2T_BACKEND_READY {"port": 51234}\r')).toEqual({ port: 51234, pid: undefined });
  });
  it.each([
    'INFO: Uvicorn running',
    'MVR2T_BACKEND_READY',
    'MVR2T_BACKEND_READY not-json',
    'MVR2T_BACKEND_READY {"port": 0}',
    'MVR2T_BACKEND_READY {"port": 70000}',
    'MVR2T_BACKEND_READY {"port": "abc"}',
  ])('ignores %j', (line) => {
    expect(parseReadyLine(line)).toBeNull();
  });
});

describe('createSessionToken / buildBackendEnv', () => {
  it('creates distinct 256-bit url-safe tokens', () => {
    const a = createSessionToken();
    const b = createSessionToken();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });
  it('passes the app data directory when given', () => {
    expect(buildBackendEnv({}, 't', ['null'], 'C:\\Users\\U\\AppData\\Roaming\\MVR2T').MVR2T_DATA_DIR).toBe(
      'C:\\Users\\U\\AppData\\Roaming\\MVR2T',
    );
    expect(buildBackendEnv({}, 't', ['null']).MVR2T_DATA_DIR).toBeUndefined();
    expect(buildBackendEnv({}, 't', ['null'], undefined, 'C:\\MVR2T\\MVR2T.exe').MVR2T_JS_RUNTIME).toBe('C:\\MVR2T\\MVR2T.exe');
    expect(buildBackendEnv({}, 't', ['null']).MVR2T_JS_RUNTIME).toBeUndefined();
  });

  it('overrides security-relevant variables from the parent env', () => {
    const env = buildBackendEnv({ PATH: '/bin', MVR2T_AUTH_TOKEN: 'old', MVR2T_BACKEND_PORT: '8765' }, 'new', ['null']);
    expect(env).toMatchObject({
      PATH: '/bin',
      MVR2T_AUTH_TOKEN: 'new',
      MVR2T_BACKEND_PORT: '0',
      MVR2T_ALLOWED_ORIGINS: 'null',
      MVR2T_EXIT_ON_STDIN_EOF: '1',
      PYTHONUTF8: '1',
    });
  });
});

// ---------------------------------------------------------------------------
// BackendManager with a fake child process
// ---------------------------------------------------------------------------

class FakeChild extends EventEmitter {
  stdin = new PassThrough();
  stdout = new PassThrough();
  stderr = new PassThrough();
  pid = 4242;
  exitCode: number | null = null;
  killed: string[] = [];
  constructor(private exitOnStdinEnd = true) {
    super();
    this.stdin.on('finish', () => this.exitOnStdinEnd && this.exit(0));
  }
  exit(code: number | null, signal: string | null = null) {
    if (this.exitCode !== null) return;
    this.exitCode = code ?? 1;
    this.emit('exit', code, signal);
  }
  kill(signal: string) {
    this.killed.push(signal);
    this.exit(null, signal);
    return true;
  }
}

function setup(opts: { resolve?: ResolveResult; healthy?: boolean; exitOnStdinEnd?: boolean; startupTimeoutMs?: number } = {}) {
  const child = new FakeChild(opts.exitOnStdinEnd ?? true);
  const states: BackendState[] = [];
  const spawn = vi.fn(() => child as unknown as ChildProcess);
  const fetch = vi.fn(async () => ({ ok: opts.healthy ?? true }));
  const manager = new BackendManager({
    resolve: () => opts.resolve ?? { ok: true, cmd: { command: '/py', args: ['-m', 'app.main'], cwd: '/b' } },
    allowedOrigins: ['null'],
    onState: (s) => states.push(s),
    spawn,
    fetch,
    env: {},
    killTree: (c) => c.kill('SIGKILL'),
    startupTimeoutMs: opts.startupTimeoutMs ?? 2000,
    stopTimeoutMs: 200,
  });
  return { child, states, spawn, fetch, manager };
}

describe('BackendManager', () => {
  it('spawns without a shell, waits for the ready line + health, then reports running', async () => {
    const { child, spawn, fetch, manager, states } = setup();
    const started = manager.start();
    child.stdout.write('INFO: starting\nMVR2T_BACKEND_READY {"port": 50123, "pid": 4242}\n');
    const state = await started;

    expect(spawn).toHaveBeenCalledWith('/py', ['-m', 'app.main'], expect.objectContaining({ shell: false, cwd: '/b', windowsHide: true }));
    expect(state.phase).toBe('running');
    expect(state.url).toBe('http://127.0.0.1:50123');
    expect(state.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:50123/api/health', expect.objectContaining({
      headers: { Authorization: `Bearer ${state.token}` },
    }));
    expect(states.map((s) => s.phase)).toEqual(['starting', 'starting', 'running']);
    expect(state.logTail).toContain('INFO: starting');
    expect(state.pid).toBe(4242); // pid from the ready line (real server, not the Windows venv launcher)
  });

  it('reports the server pid from the ready line when it differs from the spawned launcher', async () => {
    const { child, manager } = setup();
    const started = manager.start();
    child.stdout.write('MVR2T_BACKEND_READY {"port": 50123, "pid": 9999}\n');
    expect((await started).pid).toBe(9999);
  });

  it('reports a readable error when python cannot be resolved', async () => {
    const { manager, spawn } = setup({ resolve: { ok: false, message: '找不到後端的 Python' } });
    const state = await manager.start();
    expect(spawn).not.toHaveBeenCalled();
    expect(state).toMatchObject({ phase: 'error', message: '找不到後端的 Python' });
  });

  it('reports spawn errors (e.g. ENOENT)', async () => {
    const { child, manager } = setup();
    const started = manager.start();
    child.emit('error', new Error('spawn ENOENT'));
    expect(await started).toMatchObject({ phase: 'error', message: '無法啟動後端：spawn ENOENT' });
  });

  it('reports an unexpected exit during startup with the log tail', async () => {
    const { child, manager } = setup();
    const started = manager.start();
    child.stderr.write('ModuleNotFoundError: No module named fastapi\n');
    child.exit(1);
    const state = await started;
    expect(state.phase).toBe('error');
    expect(state.message).toContain('代碼 1');
    expect(state.logTail.join('\n')).toContain('ModuleNotFoundError');
  });

  it('reports a crash after it was running', async () => {
    const { child, manager, states } = setup();
    const started = manager.start();
    child.stdout.write('MVR2T_BACKEND_READY {"port": 50123}\n');
    await started;
    child.exit(null, 'SIGSEGV');
    expect(states.at(-1)).toMatchObject({ phase: 'error', url: null, token: null });
    expect(states.at(-1)?.message).toContain('SIGSEGV');
  });

  it('times out when health never passes, and kills the process', async () => {
    const { child, manager } = setup({ healthy: false, startupTimeoutMs: 300, exitOnStdinEnd: false });
    const started = manager.start();
    child.stdout.write('MVR2T_BACKEND_READY {"port": 50123}\n');
    const state = await started;
    expect(state.phase).toBe('error');
    expect(state.message).toContain('沒有就緒');
    expect(child.killed).toEqual(['SIGKILL']);
  });

  it('stops gracefully by closing stdin', async () => {
    const { child, manager } = setup();
    const started = manager.start();
    child.stdout.write('MVR2T_BACKEND_READY {"port": 50123}\n');
    await started;
    await manager.stop();
    expect(child.killed).toEqual([]); // exited on its own after stdin EOF
    expect(manager.getState()).toMatchObject({ phase: 'stopped', pid: null, url: null, token: null });
  });

  it('force-kills when the backend ignores stdin EOF', async () => {
    const { child, manager } = setup({ exitOnStdinEnd: false });
    const started = manager.start();
    child.stdout.write('MVR2T_BACKEND_READY {"port": 50123}\n');
    await started;
    await manager.stop();
    expect(child.killed).toEqual(['SIGKILL']);
    expect(manager.getState().phase).toBe('stopped');
  });

  it('restart issues a fresh token', async () => {
    const children = [new FakeChild(), new FakeChild()];
    let n = 0;
    const manager = new BackendManager({
      resolve: () => ({ ok: true, cmd: { command: '/py', args: [], cwd: '/b' } }),
      allowedOrigins: ['null'],
      onState: () => undefined,
      spawn: () => children[n++] as unknown as ChildProcess,
      fetch: async () => ({ ok: true }),
      env: {},
      killTree: (c) => c.kill('SIGKILL'),
      stopTimeoutMs: 200,
    });
    const first = manager.start();
    children[0].stdout.write('MVR2T_BACKEND_READY {"port": 1111}\n');
    const a = await first;
    const second = manager.restart();
    await new Promise((r) => setTimeout(r, 20));
    children[1].stdout.write('MVR2T_BACKEND_READY {"port": 2222}\n');
    const b = await second;
    expect(b).toMatchObject({ phase: 'running', url: 'http://127.0.0.1:2222' });
    expect(b.token).not.toBe(a.token);
  });

  it('stop() when nothing is running is a no-op', async () => {
    const { manager } = setup();
    await expect(manager.stop()).resolves.toBeUndefined();
  });
});
