"""Phase 03: process lifecycle as Electron drives it (real subprocess, no mocks).

Windows note: when the interpreter is the venv's Scripts\\python.exe, that file is only a
launcher which starts the real interpreter as a child process. So the PID we spawn (launcher)
can differ from the PID the server reports in its ready line (real server). The tests below
track the server PID separately and check that it is really gone at the end (no orphan).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.core.config import READY_MARKER

BACKEND_DIR = Path(__file__).resolve().parents[1]
TOKEN = "lifecycle-token"


def pid_alive(pid: int) -> bool:
    """Cross-platform liveness check that never sends a signal.

    (On Windows, os.kill(pid, 0) would TERMINATE the process, so it must not be used.)
    """
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # A zombie (exited, not yet reaped) counts as dead.
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as f:
            return ") Z " not in f.read()
    except OSError:
        return True  # no /proc (macOS): os.kill succeeded, so it exists


def wait_dead(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def kill_tree(proc: subprocess.Popen[str]) -> None:
    """Test cleanup only: kill the launcher AND the real server on Windows."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        proc.kill()
    proc.wait(timeout=10)


def start_backend(**extra_env: str) -> tuple[subprocess.Popen[str], int, int]:
    """Start the backend like Electron does. Returns (process, port, server_pid)."""
    import tempfile

    env = {
        **os.environ,
        # never touch the developer's real %APPDATA%\\MVR2T (session cleanup runs at startup)
        "MVR2T_DATA_DIR": tempfile.mkdtemp(prefix="mvr2t-lifecycle-"),
        "MVR2T_BACKEND_PORT": "0",
        "MVR2T_AUTH_TOKEN": TOKEN,
        "MVR2T_EXIT_ON_STDIN_EOF": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        **extra_env,
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=BACKEND_DIR,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdout is not None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        if line.startswith(READY_MARKER):
            info = json.loads(line[len(READY_MARKER):].strip())
            server_pid = int(info["pid"])
            if sys.platform != "win32":
                # Only on POSIX is the spawned process always the server itself.
                assert server_pid == proc.pid
            assert pid_alive(server_pid)
            return proc, int(info["port"]), server_pid
    kill_tree(proc)
    raise AssertionError("backend never announced readiness")


def get_health(port: int, token: str | None) -> int:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    deadline = time.monotonic() + 10
    while True:
        try:
            with urllib.request.urlopen(req, timeout=2) as res:
                return res.status
        except urllib.error.HTTPError as err:
            return err.code
        except urllib.error.URLError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def test_dynamic_port_token_and_exit_on_stdin_close():
    proc, port, server_pid = start_backend()
    try:
        assert port not in (0, 8765)
        assert get_health(port, TOKEN) == 200
        assert get_health(port, None) == 401
        # Electron quitting (or crashing) closes the pipe; the backend must exit by itself.
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
        assert wait_dead(server_pid), "real server process is still running (orphan)"
    finally:
        kill_tree(proc)


def test_two_instances_get_different_ports():
    a, port_a, _ = start_backend()
    b, port_b, _ = start_backend()
    try:
        assert port_a != port_b
    finally:
        for p in (a, b):
            assert p.stdin is not None
            p.stdin.close()
            try:
                p.wait(timeout=10)
            finally:
                kill_tree(p)


def test_listens_on_loopback_only():
    proc, port, _ = start_backend()
    try:
        assert get_health(port, TOKEN) == 200
        # Find a non-loopback address of this machine, if any, and make sure it's refused.
        hostname_ips = {ip for *_, (ip, *_rest) in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        external = [ip for ip in hostname_ips if not ip.startswith("127.")]
        for ip in external:
            s = socket.socket()
            s.settimeout(1)
            try:
                assert s.connect_ex((ip, port)) != 0
            finally:
                s.close()
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        finally:
            kill_tree(proc)


def test_exits_when_parent_dies_and_stdout_is_broken():
    """Regression: when Electron crashes, BOTH stdin and stdout pipes are gone.

    The watchdog used to print before requesting shutdown; the print raised
    BrokenPipeError, killed the watchdog thread and left an orphan backend.
    """
    proc, port, server_pid = start_backend()
    try:
        assert get_health(port, TOKEN) == 200
        assert proc.stdout is not None and proc.stdin is not None
        proc.stdout.close()  # nobody reads the backend's output any more
        proc.stdin.close()   # ...and stdin hits EOF
        assert proc.wait(timeout=10) is not None
        assert wait_dead(server_pid), "real server process is still running (orphan)"
    finally:
        kill_tree(proc)
