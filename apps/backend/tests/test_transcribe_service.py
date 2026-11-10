"""Phase 05: transcription workflow with FAKE models + real FFmpeg (fast, runs everywhere FFmpeg exists).

Verifies orchestration: sequential model loading (ASR unloaded before aligner loads), progress,
cancellation, time offsets (segment start + local time), overlap de-duplication, Traditional Chinese
output, fallbacks when the aligner is missing or the language is unsupported, and API errors.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.engines.asr.qwen3 import AsrResult
from app.engines.asr.text import Unit
from app.main import create_app
from app.api import models as models_api
from app.models import store
from app.models.registry import LLM_MODEL, QWEN3_ASR_0_6B
from app.services import transcribe as transcribe_service
from app.engines.asr.pipeline import Engines
from tests.test_media_api import LOC, extract, new_session, upload, wait_task, write_signal_wav

pytestmark = pytest.mark.skipif(LOC is None, reason="FFmpeg / ffprobe not installed")

RATE = 16000


class Log:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.loaded: set[str] = set()
        self.max_loaded = 0

    def add(self, e: str) -> None:
        self.events.append(e)


class FakeAsr:
    """Returns a fixed sentence per segment; language and delay are configurable."""

    def __init__(self, log: Log, language: str = "Chinese", delay: float = 0.0, texts: list[str] | None = None) -> None:
        self.log, self.language, self.delay, self.texts, self.calls = log, language, delay, texts, 0

    def load(self) -> None:
        self.log.add("asr.load")
        self.log.loaded.add("asr")
        self.log.max_loaded = max(self.log.max_loaded, len(self.log.loaded))

    def transcribe(self, audio: np.ndarray, language, is_cancelled) -> AsrResult:
        deadline = time.monotonic() + self.delay
        while time.monotonic() < deadline:
            if is_cancelled():
                return AsrResult(self.language, "", False)
            time.sleep(0.01)
        text = self.texts[self.calls] if self.texts else "这是软件测试。第二句话。"
        self.calls += 1
        self.log.add(f"asr.transcribe({len(audio) / RATE:.1f}s)")
        return AsrResult(language or self.language, text, False)

    def unload(self) -> None:
        self.log.add("asr.unload")
        self.log.loaded.discard("asr")


class FakeAligner:
    """Spreads characters evenly over the first 80 % of the segment (times are segment-local)."""

    def __init__(self, log: Log, fail: bool = False) -> None:
        self.log, self.fail = log, fail

    def load(self) -> None:
        self.log.add("aligner.load")
        self.log.loaded.add("aligner")
        self.log.max_loaded = max(self.log.max_loaded, len(self.log.loaded))

    def align(self, audio: np.ndarray, text: str, language: str) -> list[Unit]:
        if self.fail:
            raise RuntimeError("boom")
        chars = [c for c in text if c.isalnum()]
        dur = len(audio) / RATE * 0.8
        step = dur / max(1, len(chars))
        self.log.add("aligner.align")
        return [Unit(c, round(i * step, 3), round((i + 1) * step, 3)) for i, c in enumerate(chars)]

    def unload(self) -> None:
        self.log.add("aligner.unload")
        self.log.loaded.discard("aligner")


def read_audio(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


@pytest.fixture()
def data_dir(tmp_path, monkeypatch) -> Path:
    """userData folder where the ASR model counts as installed.

    Patches the installed-check instead of creating placeholder model files: a 1.5 GB file made with
    truncate() is sparse on Linux, but on Windows/NTFS the space is really allocated (and pytest keeps
    the temp folders of the last 3 runs), which could fill the developer's disk.
    """
    real = store.is_installed

    def fake_is_installed(spec, root):
        return spec.id == QWEN3_ASR_0_6B.id or real(spec, root)

    monkeypatch.setattr(transcribe_service, "is_installed", fake_is_installed)
    monkeypatch.setattr(models_api, "is_installed", fake_is_installed)
    return tmp_path / "userData"


def make_client(data_dir: Path, engines: Engines) -> TestClient:
    app = create_app(Settings(auth_token="", data_dir=data_dir))
    app.state.engines_factory = lambda cfg: engines
    return TestClient(app)


@pytest.fixture(scope="module")
def two_segment_wav(tmp_path_factory) -> Path:
    # 60 s with a pause at 30.0-31.0 -> silence cut at 30.5 -> segments [0, 30.5] and [30.5, 60]
    p = tmp_path_factory.mktemp("asr") / "talk.wav"
    write_signal_wav(p, 60.0, [(30.0, 31.0)], [])
    return p


@pytest.fixture(scope="module")
def hard_cut_wav(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("asr") / "continuous.wav"
    write_signal_wav(p, 70.0, [], [])  # no pauses -> hard cuts at 30 (overlap 29-30) and 59
    return p


def prepare(c: TestClient, wav: Path) -> tuple[str, str, dict]:
    sid = new_session(c)
    info = upload(c, sid, wav).json()
    result = extract(c, sid, info["media_id"])
    return sid, info["media_id"], result


def transcribe(c: TestClient, sid: str, media_id: str, language=None) -> dict:
    r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": media_id, "language": language})
    assert r.status_code == 200, r.text
    return wait_task(c, sid, r.json()["task_id"], timeout=60)


def test_full_flow_sequential_loading_offsets_and_traditional(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log), aligner=lambda: FakeAligner(log), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, extracted = prepare(c, two_segment_wav)
        segs = extracted["segments"]
        assert len(segs) == 2
        state = transcribe(c, sid, mid)
        assert state["status"] == "completed", state.get("message")
        assert state["result"]["timing"] == "aligned" and state["result"]["language"] == "Chinese"
        # Per-step durations for the workspace card. Regression: the dict was overwritten by the set of sentence
        # timings and reached the UI as ["aligned", ...]. (Only the worker-process path fills it in; the in-process
        # fake engines used here leave it empty, so check the type and the allowed keys.)
        timings = state["result"]["timings"]
        assert isinstance(timings, dict) and set(timings) <= {"asr_seconds", "align_seconds"}

        # §5.4 sequential loading: never both models in memory, ASR unloaded before aligner loads
        assert log.max_loaded == 1
        ev = [e for e in log.events if not e.startswith(("asr.transcribe", "aligner.align"))]
        assert ev == ["asr.load", "asr.unload", "aligner.load", "aligner.unload"]

        t = c.get("/api/transcript", params={"session_id": sid, "media_id": mid}).json()
        texts = [s["text"] for s in t["segments"]]
        assert texts == ["這是軟體測試。", "第二句話。"] * 2  # Simplified -> Traditional (Taiwan phrasing)
        # times map back to the ORIGINAL file: second segment's sentences start after its offset
        second = t["segments"][2:]
        assert all(s["start"] >= segs[1]["start"] for s in second)
        assert t["segments"][0]["start"] == 0.0
        words = t["segments"][2]["words"]
        assert words[0]["text"] == "這" and words[0]["start"] == pytest.approx(segs[1]["start"], abs=0.001)
        for a, b in zip(t["segments"], t["segments"][1:]):
            assert b["start"] >= a["start"]


def test_hard_cut_overlap_is_not_duplicated(data_dir, hard_cut_wav):
    log = Log()
    # every segment "hears" the same sentence; with real audio the overlap content repeats at the boundary
    engines = Engines(asr=lambda: FakeAsr(log, texts=["甲乙丙丁。"] * 3), aligner=lambda: FakeAligner(log), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, extracted = prepare(c, hard_cut_wav)
        assert [s["boundary"] for s in extracted["segments"]] == ["hard", "hard", "end"]
        transcribe(c, sid, mid)
        t = c.get("/api/transcript", params={"session_id": sid, "media_id": mid}).json()
        # each fake segment "hears" 甲乙丙丁 starting at its own start; 甲 of segments 1 and 2 lies before the
        # overlap midpoint, so it belongs to the previous segment and is trimmed (word-level de-duplication)
        assert [s["text"] for s in t["segments"]] == ["甲乙丙丁。", "乙丙丁。", "乙丙丁。"]
        starts = [s["start"] for s in t["segments"]]
        assert starts == sorted(starts) and starts[1] > 29.5


def test_without_aligner_times_are_estimated(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log), aligner=None, read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        state = transcribe(c, sid, mid)
        assert state["result"]["timing"] == "estimated"
        assert any("對齊模型" in w for w in state["result"]["warnings"])
        assert "aligner.load" not in log.events


def test_unsupported_language_falls_back_to_estimated(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log, language="Thai"), aligner=lambda: FakeAligner(log), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        state = transcribe(c, sid, mid)
        assert state["result"]["timing"] == "estimated"
        assert any("Thai" in w for w in state["result"]["warnings"])
        assert "aligner.load" not in log.events  # nothing to align -> aligner never loaded


def test_aligner_failure_on_a_segment_degrades_gracefully(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log), aligner=lambda: FakeAligner(log, fail=True), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        state = transcribe(c, sid, mid)
        assert state["status"] == "completed" and state["result"]["timing"] == "estimated"
        assert log.events[-1] == "aligner.unload"


def test_forced_language_is_passed_and_reported(data_dir, two_segment_wav):
    log = Log()
    seen: list = []

    class Recording(FakeAsr):
        def transcribe(self, audio, language, is_cancelled):
            seen.append(language)
            return super().transcribe(audio, language, is_cancelled)

    engines = Engines(asr=lambda: Recording(log, language="English", texts=["Hello there.", "Bye."]), aligner=None, read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        state = transcribe(c, sid, mid, language="English")
        assert seen == ["English", "English"] and state["result"]["language"] == "English"
        t = c.get("/api/transcript", params={"session_id": sid, "media_id": mid}).json()
        assert [s["text"] for s in t["segments"]] == ["Hello there.", "Bye."]  # English is not converted


def test_cancel_during_recognition_unloads_model(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log, delay=5.0), aligner=lambda: FakeAligner(log), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        task_id = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid}).json()["task_id"]
        time.sleep(0.3)
        st = c.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
        assert st["status"] == "running" and st["stage"] == "正在辨識語音"
        started = time.monotonic()
        c.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
        st = wait_task(c, sid, task_id, timeout=5)
        assert st["status"] == "cancelled" and time.monotonic() - started < 2
        assert log.events[-1] == "asr.unload" and "aligner.load" not in log.events
        assert c.get("/api/transcript", params={"session_id": sid, "media_id": mid}).status_code == 404
        # a new transcription can start right away (global lock released)
        assert c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid}).status_code == 200


def test_progress_reaches_each_stage(data_dir, two_segment_wav):
    log = Log()
    stages: list[str] = []
    engines = Engines(asr=lambda: FakeAsr(log, delay=0.4), aligner=lambda: FakeAligner(log), read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        task_id = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid}).json()["task_id"]
        last = -1.0
        while True:
            st = c.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
            assert st["progress"] >= last  # never goes backwards
            last = st["progress"]
            if st["stage"] and (not stages or stages[-1] != st["stage"]):
                stages.append(st["stage"])
            if st["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.05)
        assert st["status"] == "completed" and st["progress"] == 1.0
        assert "正在辨識語音" in stages and stages[-1] == "完成"


def test_api_errors(data_dir, tmp_path, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log, delay=1.0), aligner=None, read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid = new_session(c)
        info = upload(c, sid, two_segment_wav).json()
        mid = info["media_id"]
        r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid})
        assert r.status_code == 409 and "抽取音訊" in r.json()["detail"]  # audio not extracted yet
        extract(c, sid, mid)
        assert c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": "nope"}).status_code == 404
        r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid, "language": "Klingon"})
        assert r.status_code == 422
        first = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid})
        assert first.status_code == 200
        assert c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid}).status_code == 409
        # re-extracting audio while transcribing is refused (it would delete the audio being read)
        assert c.post("/api/media/extract-audio", json={"session_id": sid, "media_id": mid}).status_code == 409
        wait_task(c, sid, first.json()["task_id"])


def test_model_not_installed(tmp_path, two_segment_wav):
    engines = Engines(asr=lambda: FakeAsr(Log()), aligner=None, read_audio=read_audio)
    with make_client(tmp_path / "empty", engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid})
        assert r.status_code == 412 and "download_models" in r.json()["detail"]
        models = c.get("/api/models").json()
        assert {m["id"]: m["installed"] for m in models["models"]} == {
            "qwen3-asr-0.6b": False, "qwen3-forcedaligner-0.6b": False, LLM_MODEL.id: False,
        }


def test_models_endpoint_reports_installed(data_dir):
    with make_client(data_dir, Engines(asr=lambda: FakeAsr(Log()), aligner=None, read_audio=read_audio)) as c:
        body = c.get("/api/models").json()
        by_id = {m["id"]: m for m in body["models"]}
        assert by_id["qwen3-asr-0.6b"]["installed"] is True
        llm = next(m for m in body["models"] if m["kind"] == "llm")
        assert llm["downloadable"] is True and llm["installed"] is False and llm["size_bytes"] > 2_000_000_000
        assert body["models_dir"].endswith("models")


def test_ending_session_cancels_transcription(data_dir, two_segment_wav):
    log = Log()
    engines = Engines(asr=lambda: FakeAsr(log, delay=5.0), aligner=None, read_audio=read_audio)
    with make_client(data_dir, engines) as c:
        sid, mid, _ = prepare(c, two_segment_wav)
        c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": mid})
        time.sleep(0.3)
        started = time.monotonic()
        new_session(c)  # e.g. user reloads the window
        assert time.monotonic() - started < 3
        assert "asr.unload" in log.events
    assert threading.active_count() < 50
