"""Phase 06 API: POST /api/summary/generate + GET /api/summary with a fake model (no llama.cpp needed)."""
from __future__ import annotations

import threading
import time

import pytest

from app.core.config import Settings
from app.main import create_app
from tests.test_llm_engine import FakeLlm
from tests.test_transcribe_service import FakeAsr, Log, data_dir, prepare, read_audio, transcribe, two_segment_wav  # noqa: F401
from app.engines.asr.pipeline import Engines
from fastapi.testclient import TestClient
from tests.test_media_api import LOC, wait_task

pytestmark = pytest.mark.skipif(LOC is None, reason="FFmpeg not installed")


class FakeServer(FakeLlm):
    """Behaves like LlamaServer: with-block = model loaded, kill() from another thread."""

    def __init__(self, events: list[str], delay: float = 0.0) -> None:
        super().__init__()
        self.events = events
        self.delay = delay
        self.killed = threading.Event()

    def __enter__(self):  # noqa: ANN204
        self.events.append("load")
        return self

    def __exit__(self, *exc: object) -> None:
        self.events.append("unload")

    def kill(self) -> None:
        self.events.append("kill")
        self.killed.set()

    def chat(self, *a, **kw):  # noqa: ANN002, ANN003
        if self.delay and self.killed.wait(self.delay):
            from app.engines.llm.server import LlmCancelled

            raise LlmCancelled()
        return super().chat(*a, **kw)


def client(data_dir, events, delay=0.0) -> TestClient:  # noqa: F811
    app = create_app(Settings(auth_token="", data_dir=data_dir))
    log = Log()
    app.state.engines_factory = lambda cfg: Engines(asr=lambda: FakeAsr(log), aligner=None, read_audio=read_audio)
    servers: list[FakeServer] = []

    def factory(cfg):  # noqa: ANN001, ANN202
        s = FakeServer(events, delay)
        servers.append(s)
        return s

    app.state.llm_factory = factory
    app.state.test_servers = servers
    return TestClient(app)


def generate(c: TestClient, sid: str, mid: str, types: list[str]):  # noqa: ANN201
    return c.post("/api/summary/generate", json={"session_id": sid, "media_id": mid, "types": types})


def test_summary_after_transcription_loads_and_unloads_the_model(data_dir, two_segment_wav):  # noqa: F811
    events: list[str] = []
    with client(data_dir, events) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        r = generate(c, sid, mid, ["overview"])
        assert r.status_code == 409 and "語音辨識" in r.json()["detail"]
        assert transcribe(c, sid, mid)["status"] == "completed"
        r = generate(c, sid, mid, ["keywords", "overview"])
        assert r.status_code == 200, r.text
        state = wait_task(c, sid, r.json()["task_id"], timeout=30)
        assert state["status"] == "completed", state
        assert events == ["load", "unload"]  # §5.4: loaded only for this task
        s = c.get("/api/summary", params={"session_id": sid, "media_id": mid}).json()
        assert s["types"] == ["overview", "keywords"]
        assert s["results"]["overview"] == "這是摘要。"
        assert s["results"]["keywords"] == ["中山店"]
        assert s["results"]["qa"] is None
        # re-transcribing invalidates the summary
        assert transcribe(c, sid, mid)["status"] == "completed"
        assert c.get("/api/summary", params={"session_id": sid, "media_id": mid}).status_code == 404


def test_rejects_unknown_or_empty_types(data_dir, two_segment_wav):  # noqa: F811
    with client(data_dir, []) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        transcribe(c, sid, mid)
        assert generate(c, sid, mid, []).status_code == 422
        r = generate(c, sid, mid, ["overview", "poem"])
        assert r.status_code == 422 and "poem" in r.json()["detail"]


def test_cancel_kills_the_model_process(data_dir, two_segment_wav):  # noqa: F811
    events: list[str] = []
    with client(data_dir, events, delay=30) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        transcribe(c, sid, mid)
        task_id = generate(c, sid, mid, ["overview"]).json()["task_id"]
        time.sleep(0.5)
        started = time.monotonic()
        c.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
        st = wait_task(c, sid, task_id, timeout=10)
        assert st["status"] == "cancelled" and time.monotonic() - started < 5
        assert "kill" in events and events[-1] == "unload"
        # the model lock was released: a new summary can start
        r = generate(c, sid, mid, ["overview"])
        assert r.status_code == 200


def test_summary_and_transcription_never_run_at_the_same_time(data_dir, two_segment_wav):  # noqa: F811
    with client(data_dir, [], delay=30) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        transcribe(c, sid, mid)
        task_id = generate(c, sid, mid, ["overview"]).json()["task_id"]
        r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid})
        assert r.status_code == 409 and "AI 工作" in r.json()["detail"]
        r = c.post("/api/media/extract-audio", json={"session_id": sid, "media_id": mid})
        assert r.status_code == 409 and "摘要" in r.json()["detail"]
        c.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
        wait_task(c, sid, task_id, timeout=10)


def test_missing_model_gives_download_instructions(data_dir, two_segment_wav):  # noqa: F811
    app = create_app(Settings(auth_token="", data_dir=data_dir))
    log = Log()
    app.state.engines_factory = lambda cfg: Engines(asr=lambda: FakeAsr(log), aligner=None, read_audio=read_audio)
    with TestClient(app) as c:  # default llm_factory (real llama.cpp), nothing installed
        sid, mid, _ = prepare(c, two_segment_wav)
        transcribe(c, sid, mid)
        r = generate(c, sid, mid, ["overview"])
        assert r.status_code == 412 and "download_models --llm" in r.json()["detail"]
