"""Phase 09: model manager (download with progress / cancel / resume, verify, repair, update, delete, unused files).

Uses a local HTTP server that behaves like Hugging Face (`/<repo>/resolve/<revision>/<file>`, Range requests),
so nothing is downloaded from the internet.

Timeouts are short here (2 s) on purpose. On the user's Windows PC (Avast installed) a loopback HTTP response
sometimes stalls even though the server has written everything (2026-11-11). The downloader must recover from that:
read timeout -> reconnect -> resume with Range. The stall/truncate tests below exercise exactly that path.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import manager as mgr
from app.models import fetch as fetch_module
from app.models import store
from app.models.fetch import FetchCancelled, FetchError, fetch
from app.models.registry import ModelFile, ModelSpec
from app.services.model_lock import MODEL_LOCK

BIG = bytes(range(256)) * 4096  # 1 MiB
SMALL = b'{"architectures": ["Test"]}'


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_sha1(b: bytes) -> str:
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()


class Server:
    """Files keyed by URL path. Records requests; can throttle, fail once, or ignore Range."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.hits: list[tuple[str, str | None]] = []
        self.delay = 0.0
        self.fail_once: set[str] = set()
        self.no_range = False
        #: paths whose next response sends half the body, then stalls (longer than the client timeout) or closes
        self.stall_once: set[str] = set()
        self.truncate_once: set[str] = set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, D401
                pass

            def do_GET(self):  # noqa: N802
                rng = self.headers.get("Range")
                outer.hits.append((self.path, rng))
                if self.path in outer.fail_once:
                    outer.fail_once.discard(self.path)
                    self.send_response(503)
                    self.end_headers()
                    return
                data = outer.files.get(self.path)
                if data is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                start = 0
                if rng and not outer.no_range:
                    start = int(rng.split("=")[1].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                step = 64 * 1024
                stall = self.path in outer.stall_once
                truncate = self.path in outer.truncate_once
                outer.stall_once.discard(self.path)
                outer.truncate_once.discard(self.path)
                for i in range(0, len(body), step):
                    if (stall or truncate) and i >= len(body) // 2:
                        if stall:
                            time.sleep(4)
                        return
                    try:
                        self.wfile.write(body[i : i + step])
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    if outer.delay:
                        time.sleep(outer.delay)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def add(self, spec: ModelSpec, contents: dict[str, bytes]) -> None:
        for name, data in contents.items():
            self.files[f"/{spec.repo}/resolve/{spec.revision}/{name}"] = data

    def gets(self, name: str) -> int:
        return sum(1 for p, _ in self.hits if p.endswith("/" + name))


def make_spec(revision: str = "rev1", big: bytes = BIG) -> ModelSpec:
    return ModelSpec(
        id="test-asr",
        kind="asr",
        display_name="Test ASR",
        role="test",
        repo="org/test-asr",
        revision=revision,
        license="MIT",
        files=(ModelFile("model.bin", len(big), "sha256", sha256(big)), ModelFile("config.json", len(SMALL), "git-sha1", git_sha1(SMALL))),
    )


@pytest.fixture(autouse=True)
def short_timeouts(monkeypatch):
    monkeypatch.setattr(fetch_module, "TIMEOUT", 2.0)
    monkeypatch.setattr(fetch_module, "BACKOFF", 0.05)


@pytest.fixture()
def server(monkeypatch):
    s = Server()
    monkeypatch.setattr(store, "HF_ENDPOINT", s.url)
    yield s
    s.httpd.shutdown()


@pytest.fixture()
def env(tmp_path, monkeypatch, server):
    spec = make_spec()
    server.add(spec, {"model.bin": BIG, "config.json": SMALL})
    pkg = mgr.Package("asr", "語音辨識", "test", "test", (spec,))
    monkeypatch.setattr(mgr, "PACKAGES", (pkg,))
    monkeypatch.setattr(mgr, "BY_PACKAGE", {"asr": pkg})
    monkeypatch.setattr(mgr, "ALL_MODELS", (spec,))
    m = mgr.ModelManager(tmp_path / "models", tmp_path / "runtime")
    yield m, spec
    m.shutdown()


def wait_idle(m: mgr.ModelManager, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = m.snapshot()
        if not snap["busy"]:
            return snap["packages"][0]
        time.sleep(0.02)
    raise AssertionError("manager still busy")


# --------------------------------------------------------------------------- fetch


def test_fetch_resumes_a_partial_file(tmp_path, server):
    server.files["/f"] = BIG
    dest = tmp_path / "f"
    dest.write_bytes(BIG[:1000])
    got: list[int] = []
    fetch(server.url + "/f", dest, len(BIG), got.append)
    assert dest.read_bytes() == BIG and sum(got) == len(BIG) - 1000
    assert server.hits[-1][1] == "bytes=1000-"


def test_fetch_restarts_when_the_server_ignores_range(tmp_path, server):
    server.files["/f"] = BIG
    server.no_range = True
    dest = tmp_path / "f"
    dest.write_bytes(BIG[:1000])
    got: list[int] = []
    fetch(server.url + "/f", dest, len(BIG), got.append)
    assert dest.read_bytes() == BIG and sum(got) == len(BIG) - 1000  # progress goes back, then forward


def test_fetch_recovers_from_a_stalled_or_truncated_response_by_resuming(tmp_path, server):
    server.files["/f"] = BIG
    for kind in ("stall_once", "truncate_once"):
        getattr(server, kind).add("/f")
        server.hits.clear()
        dest = tmp_path / kind
        got: list[int] = []
        fetch(server.url + "/f", dest, len(BIG), got.append)
        assert dest.read_bytes() == BIG and sum(got) == len(BIG)
        assert len(server.hits) == 2 and server.hits[1][1] and server.hits[1][1].startswith("bytes=")  # resumed


def test_fetch_gives_up_only_after_repeated_failures_without_progress(tmp_path, server):
    server.files["/f"] = SMALL
    tries = {"n": 0}

    class AlwaysFail(set):
        """Every request answers 503."""

        def __contains__(self, item):  # noqa: ANN001
            tries["n"] += 1
            return True

        def discard(self, item):  # noqa: ANN001
            pass

    server.fail_once = AlwaysFail()
    with pytest.raises(FetchError, match="伺服器回應錯誤"):
        fetch(server.url + "/f", tmp_path / "f", len(SMALL), retries=2)
    assert tries["n"] == 3  # 1 try + 2 retries


def test_fetch_retries_server_errors_and_explains_missing_files(tmp_path, server):
    server.files["/f"] = SMALL
    server.fail_once.add("/f")
    fetch(server.url + "/f", tmp_path / "f", len(SMALL), sleep=lambda s: None)
    assert (tmp_path / "f").read_bytes() == SMALL
    with pytest.raises(FetchError, match="404"):
        fetch(server.url + "/missing", tmp_path / "g", 10, sleep=lambda s: None)
    with pytest.raises(FetchError, match="無法連線"):
        fetch("http://127.0.0.1:1/x", tmp_path / "h", 10, retries=1, sleep=lambda s: None)


def test_fetch_can_be_cancelled(tmp_path, server):
    server.files["/f"] = BIG
    server.delay = 0.01
    seen = []
    with pytest.raises(FetchCancelled):
        fetch(server.url + "/f", tmp_path / "f", len(BIG), seen.append, is_cancelled=lambda: len(seen) > 0)
    assert 0 < (tmp_path / "f").stat().st_size < len(BIG)


# --------------------------------------------------------------------------- manager


def test_download_shows_progress_and_installs_after_verification(env, server):
    m, spec = env
    assert m.snapshot()["packages"][0]["status"] == "not_installed"
    server.delay = 0.005
    m.request("asr", "download")
    seen_progress = False
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        p = m.snapshot()["packages"][0]
        if p["job"] and p["job"]["done_bytes"] > 0:
            seen_progress = p["status"] == "downloading" and p["job"]["total_bytes"] == spec.size_bytes
            break
        time.sleep(0.01)
    p = wait_idle(m)
    assert seen_progress
    assert p["status"] == "installed" and p["last"]["ok"] and p["missing_bytes"] == 0
    assert store.is_installed(spec, m.models_root)
    assert not store.staging_dir(spec, m.models_root).exists()
    with pytest.raises(mgr.ManagerError):
        m.request("asr", "download")  # already installed


def test_cancel_keeps_the_partial_download_and_the_next_download_continues(env, server):
    m, spec = env
    server.delay = 0.01
    m.request("asr", "download")
    while not (m.snapshot()["packages"][0]["job"] or {}).get("done_bytes"):
        time.sleep(0.01)
    m.cancel("asr")
    p = wait_idle(m)
    assert p["status"] == "partial" and "已取消" in p["last"]["message"]
    assert 0 < p["missing_bytes"] < spec.size_bytes
    server.delay = 0
    server.hits.clear()
    m.request("asr", "download")
    assert wait_idle(m)["status"] == "installed"
    assert server.hits[0][1] and server.hits[0][1].startswith("bytes=")  # resumed, not restarted


def test_verify_finds_damage_and_repair_downloads_only_the_bad_file(env, server):
    m, spec = env
    m.request("asr", "download")
    wait_idle(m)
    m.request("asr", "verify")
    p = wait_idle(m)
    assert p["status"] == "installed" and p["last"]["action"] == "verify" and p["last"]["ok"]
    model = spec.local_dir(m.models_root) / "model.bin"
    data = bytearray(model.read_bytes())
    data[10] ^= 0xFF  # same size, different content: only a full verification notices
    model.write_bytes(bytes(data))
    m.request("asr", "verify")
    p = wait_idle(m)
    assert p["status"] == "damaged" and not p["last"]["ok"] and "雜湊不符" in p["last"]["problems"][0]
    server.hits.clear()
    m.request("asr", "download")  # 「修復」
    p = wait_idle(m)
    assert p["status"] == "installed", p
    assert server.gets("model.bin") == 1 and server.gets("config.json") == 0
    assert store.verify_installed(spec, m.models_root) == []


def test_new_version_is_outdated_and_update_reuses_unchanged_files(env, server, monkeypatch):
    m, spec = env
    m.request("asr", "download")
    wait_idle(m)
    v2 = make_spec("rev2", big=BIG[::-1])
    server.add(v2, {"model.bin": BIG[::-1], "config.json": SMALL})
    pkg = mgr.Package("asr", "語音辨識", "test", "test", (v2,))
    monkeypatch.setattr(mgr, "PACKAGES", (pkg,))
    monkeypatch.setattr(mgr, "BY_PACKAGE", {"asr": pkg})
    monkeypatch.setattr(mgr, "ALL_MODELS", (v2,))
    p = m.snapshot()["packages"][0]
    assert p["status"] == "outdated" and p["models"][0]["installed_revision"] == "rev1"
    server.hits.clear()
    m.request("asr", "download")
    p = wait_idle(m)
    assert p["status"] == "installed" and store.installed_revision(v2, m.models_root) == "rev2"
    assert server.gets("model.bin") == 1 and server.gets("config.json") == 0  # config.json unchanged -> reused


def test_delete_waits_for_ai_work_and_removes_everything(env):
    m, spec = env
    m.request("asr", "download")
    wait_idle(m)
    assert MODEL_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(mgr.ManagerError, match="正在使用"):
            m.delete("asr")
    finally:
        MODEL_LOCK.release()
    m.delete("asr")
    assert m.snapshot()["packages"][0]["status"] == "not_installed"
    assert not spec.local_dir(m.models_root).exists()


def test_unused_models_and_old_runtimes_are_listed_and_can_be_deleted(env):
    m, _ = env
    old = m.models_root / "llm" / "qwen3-4b-q4_k_m"
    old.mkdir(parents=True)
    (old / "x.gguf").write_bytes(b"x" * 100)
    old_rt = m.runtime_root / "llama" / "b6000-win-cpu-x64"
    old_rt.mkdir(parents=True)
    (old_rt / "llama-server.exe").write_bytes(b"y" * 10)
    items = {u["key"]: u for u in m.unused()}
    assert items["models/llm/qwen3-4b-q4_k_m"]["size_bytes"] == 100
    assert "runtime/llama/b6000-win-cpu-x64" in items
    with pytest.raises(mgr.ManagerError):
        m.delete_unused("models/../../etc")
    m.delete_unused("models/llm/qwen3-4b-q4_k_m")
    m.delete_unused("runtime/llama/b6000-win-cpu-x64")
    assert not old.exists() and not old_rt.exists() and m.unused() == []


def test_disk_space_is_checked_before_downloading(env, monkeypatch):
    m, _ = env

    class Usage:
        free = 10

    monkeypatch.setattr(store.shutil, "disk_usage", lambda p: Usage)
    m.request("asr", "download")
    p = wait_idle(m)
    assert not p["last"]["ok"] and "磁碟空間不足" in p["last"]["message"]


# --------------------------------------------------------------------------- API


def test_api_download_progress_verify_and_delete(env, tmp_path):
    m, _ = env
    app = create_app(Settings(auth_token="", data_dir=tmp_path / "userData"))
    app.state.model_manager = m
    with TestClient(app) as c:
        body = c.get("/api/models").json()
        assert body["packages"][0]["status"] == "not_installed" and body["busy"] is False
        assert c.post("/api/models/asr/verify").status_code == 409
        assert c.post("/api/models/nope/download").status_code == 404
        r = c.post("/api/models/download-all")
        assert r.status_code == 200 and r.json()["busy"] is True
        deadline = time.monotonic() + 20
        while c.get("/api/models").json()["busy"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert c.get("/api/models").json()["packages"][0]["status"] == "installed"
        assert c.delete("/api/models/unused/models/llm/nothing").status_code == 404
        assert c.delete("/api/models/asr").status_code == 204
        assert c.get("/api/models").json()["packages"][0]["status"] == "not_installed"
        legacy = c.get("/api/models/legacy").json()
        assert "models" in legacy and "runtimes" in legacy
        json.dumps(body)  # serialisable


def test_installed_models_never_touch_the_network(env, monkeypatch):
    """Acceptance: offline after download; without network nothing is re-downloaded."""
    m, spec = env
    m.request("asr", "download")
    wait_idle(m)

    def no_network(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("network used")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    for _ in range(3):
        assert m.snapshot()["packages"][0]["status"] == "installed"
    with pytest.raises(mgr.ManagerError, match="已安裝"):
        m.request("asr", "download")
    m.request("asr", "verify")  # verification is local only
    assert wait_idle(m)["last"]["ok"]


def test_a_stalled_connection_during_a_model_download_recovers_by_itself(env, server):
    m, spec = env
    server.stall_once.add(f"/{spec.repo}/resolve/{spec.revision}/model.bin")
    m.request("asr", "download")
    p = wait_idle(m)
    assert p["status"] == "installed" and p["last"]["ok"]
    assert sum(1 for path, rng in server.hits if path.endswith("model.bin") and rng) == 1  # resumed once
