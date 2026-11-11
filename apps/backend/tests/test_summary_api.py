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


def test_regenerating_the_mindmap_keeps_the_other_summary_results(data_dir, two_segment_wav):  # noqa: F811
    events: list[str] = []
    with client(data_dir, events) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        transcribe(c, sid, mid)
        wait_task(c, sid, generate(c, sid, mid, ["overview", "mindmap"]).json()["task_id"], timeout=30)
        s = c.get("/api/summary", params={"session_id": sid, "media_id": mid}).json()
        assert s["types"] == ["overview", "mindmap"] and s["results"]["mindmap"]["kind"] == "central"
        r = c.post("/api/mindmap/generate", json={"session_id": sid, "media_id": mid})
        assert r.status_code == 200, r.text
        assert wait_task(c, sid, r.json()["task_id"], timeout=30)["status"] == "completed"
        s2 = c.get("/api/summary", params={"session_id": sid, "media_id": mid}).json()
        assert s2["types"] == ["overview", "mindmap"]
        assert s2["results"]["overview"] == s["results"]["overview"]  # kept
        assert events == ["load", "unload", "load", "unload"]


def test_export_api_returns_files_for_the_current_session(data_dir, two_segment_wav):  # noqa: F811
    """Phase 08: POST /api/export (CSV with BOM, DOCX, print HTML, segment ZIP); clear errors before data exists."""
    import io
    import zipfile

    events: list[str] = []
    with client(data_dir, events) as c:
        sid, mid, _ = prepare(c, two_segment_wav)

        def export(content: str, fmt: str, **extra):  # noqa: ANN003, ANN202
            return c.post("/api/export", json={"session_id": sid, "media_id": mid, "content": content, "format": fmt, **extra})

        r = export("transcript", "txt")
        assert r.status_code == 404 and "語音辨識" in r.json()["detail"]
        r = export("segments", "csv")
        assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and r.headers["content-type"].startswith("text/csv")
        z = zipfile.ZipFile(io.BytesIO(export("segments_audio", "zip").content))
        assert z.namelist()[-1] == "segments.csv" and all(n.startswith("seg_") for n in z.namelist()[:-1])
        assert export("segments", "srt").status_code == 422
        assert transcribe(c, sid, mid)["status"] == "completed"
        assert export("transcript", "srt").text.startswith("1\r\n00:00:")
        assert export("transcript", "docx").content[:2] == b"PK"
        r = generate(c, sid, mid, ["overview", "mindmap"])
        assert wait_task(c, sid, r.json()["task_id"], timeout=30)["status"] == "completed"
        edited = {"id": "n", "text": "我改過的中心", "kind": "central", "refs": [], "time": None, "children": []}
        md = export("summary", "md", mindmap=edited).text
        assert "## 全文摘要" in md and "我改過的中心" in md
        assert "<!DOCTYPE html>" in export("summary", "html").text
        assert export("summary", "md", mindmap_png="!!").status_code == 422
        assert c.post("/api/export", json={"session_id": sid, "media_id": "other", "content": "summary", "format": "md"}).status_code == 404
