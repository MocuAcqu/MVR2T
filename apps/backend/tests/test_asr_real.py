"""Phase 05 acceptance with the REAL models (Qwen3-ASR-0.6B + Qwen3-ForcedAligner-0.6B) on CPU.

Skipped unless all of these are available:
- the models are installed (python -m scripts.download_models),
- torch + transformers are installed,
- MVR2T_TEST_SPEECH_DIR points to a folder with test speech:
    zh16.wav            Mandarin speech, 16 kHz mono (script in zh_text.txt)
    en_0.wav..en_5.wav  six English utterances, 16 kHz mono
    en_refs.json        their reference transcripts (list of 6 strings)
  (The sandbox builds these from LibriSpeech and Piper TTS; audio is not committed to the repo.)

Acceptance (PROJECT_SPEC Phase 05): transcript displays correctly; timestamps map to the original audio;
cancellable; long audio does not crash.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, default_user_data_dir
from app.core.procmem import current_rss_mb
from app.main import create_app
from app.models.registry import QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B
from app.models.store import is_installed
from tests.test_media_api import LOC, extract, new_session, upload, wait_task

SPEECH = Path(os.environ.get("MVR2T_TEST_SPEECH_DIR", "/nonexistent"))
MODELS_DATA = Path(os.environ.get("MVR2T_DATA_DIR") or default_user_data_dir())

# find_spec checks availability WITHOUT importing torch, so the memory test below can assert that the
# backend process itself never loads it.
HAVE_TORCH = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("transformers") is not None

pytestmark = [
    pytest.mark.skipif(LOC is None, reason="FFmpeg not installed"),
    pytest.mark.skipif(not HAVE_TORCH, reason="torch/transformers not installed"),
    pytest.mark.skipif(
        not (is_installed(QWEN3_ASR_0_6B, MODELS_DATA / "models") and is_installed(QWEN3_FORCED_ALIGNER_0_6B, MODELS_DATA / "models")),
        reason="models not downloaded",
    ),
    pytest.mark.skipif(not (SPEECH / "zh16.wav").exists(), reason="MVR2T_TEST_SPEECH_DIR not set"),
]


@pytest.fixture()
def client(tmp_path):
    # Models from the real folder, session temp in a throwaway folder. models_dir points straight at the
    # real models (no symlink: creating symlinks on Windows needs Developer Mode or admin rights).
    real_models = MODELS_DATA / "models"
    app = create_app(Settings(auth_token="", data_dir=tmp_path / "userData", models_dir=real_models))

    from app.engines.asr.worker import EngineSpec

    def engines(_cfg):
        # the production path: models run in a separate worker process
        return EngineSpec(
            str(QWEN3_ASR_0_6B.local_dir(real_models)),
            str(QWEN3_FORCED_ALIGNER_0_6B.local_dir(real_models)),
            _cfg.asr_dtype,
            _cfg.torch_threads,
        )

    app.state.engines_factory = engines
    with TestClient(app) as c:
        yield c


def run(c, path: Path, language=None) -> tuple[dict, dict]:
    sid = new_session(c)
    info = upload(c, sid, path).json()
    extracted = extract(c, sid, info["media_id"])
    r = c.post("/api/asr/transcribe", json={"session_id": sid, "media_id": info["media_id"], "language": language})
    assert r.status_code == 200, r.text
    state = wait_task(c, sid, r.json()["task_id"], timeout=900)
    assert state["status"] == "completed", state.get("message")
    t = c.get("/api/transcript", params={"session_id": sid, "media_id": info["media_id"]}).json()
    return extracted, {**t, "task": state["result"]}


_SPOKEN = {"mr": "mister", "mrs": "missus", "dr": "doctor", "st": "saint"}  # LibriSpeech spells titles out


def _words(s: str) -> list[str]:
    return [_SPOKEN.get(w, w) for w in re.findall(r"[a-z0-9']+", s.lower())]


def _wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[-1] / max(1, len(ref))


def test_mandarin_traditional_output_with_character_timestamps(client):
    _, t = run(client, SPEECH / "zh16.wav")
    text = "".join(s["text"] for s in t["segments"])
    print("\nZH:", text, "\n", t["task"])
    assert t["language"] == "Chinese" and t["timing"] == "aligned"
    # Traditional characters (Taiwan phrasing), never Simplified
    for trad in ["們", "語音", "錄音", "摘要", "內容", "複習"]:
        assert trad in text, trad
    for simp in ["们", "语音", "录音"]:
        assert simp not in text
    assert len(t["segments"]) == 4  # four sentences in the script
    starts = [s["start"] for s in t["segments"]]
    assert starts == sorted(starts) and starts[0] < 0.5 and t["segments"][-1]["end"] <= t["duration"] + 0.05
    words = [w for s in t["segments"] for w in s["words"]]
    assert all(len(w["text"]) == 1 for w in words)  # character-level for Chinese


def test_english_timestamps_map_back_to_the_original_audio(client, tmp_path):
    refs = json.loads((SPEECH / "en_refs.json").read_text())
    clips = [SPEECH / f"en_{i}.wav" for i in range(6)]
    starts, pos = [], 0.0
    for p in clips:
        starts.append(pos)
        with wave.open(str(p)) as w:
            pos += w.getnframes() / w.getframerate()
    lst = tmp_path / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in clips))
    combined = tmp_path / "en_concat.wav"
    subprocess.run([str(LOC.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", str(combined)], check=True)

    extracted, t = run(client, combined)
    print("\nEN segments:", [(s["start"], s["end"], s["boundary"]) for s in extracted["segments"]], "\n", t["task"])
    assert len(extracted["segments"]) >= 2  # spans several ASR segments -> offsets really matter
    assert t["language"] == "English" and t["timing"] == "aligned"

    hyp = _words(" ".join(s["text"] for s in t["segments"]))
    wer = _wer(_words(" ".join(refs)), hyp)
    print(f"WER {wer:.1%}")
    assert wer < 0.15

    # Each clip must begin where it starts in the combined file. Match one of its first three words
    # (proper names may be spelled differently, e.g. LINNELL'S vs Linel's) within the clip's first 2 s.
    words = [w for s in t["segments"] for w in s["words"]]
    for i, (ref, clip_start) in enumerate(zip(refs, starts)):
        found = None
        for k, target in enumerate(_words(ref)[:3]):
            hits = [w for w in words if _words(w["text"]) == [target] and clip_start - 0.3 <= w["start"] <= clip_start + 2.0]
            if hits:
                found = (k, target, hits[0]["start"])
                break
        if found is None:
            near = [(w["text"], w["start"]) for w in words if clip_start - 2 <= w["start"] <= clip_start + 3]
            print(f"clip {i}: ref starts {ref[:60]!r}; words near {clip_start:.2f}s: {near}")
        assert found, f"clip {i} not found near {clip_start:.2f}s"
        print(f"clip {i}: word #{found[0] + 1} '{found[1]}' expected ≥{clip_start:.2f}s, found {found[2]:.2f}s")


def test_cancel_real_model_mid_recognition(client):
    sid = new_session(client)
    info = upload(client, sid, SPEECH / "zh16.wav").json()
    extract(client, sid, info["media_id"])
    task_id = client.post("/api/asr/transcribe", json={"session_id": sid, "media_id": info["media_id"]}).json()["task_id"]
    import time

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        st = client.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
        if st["stage"] == "正在辨識語音":
            break
        time.sleep(0.1)
    time.sleep(1.0)  # inside generate()
    started = time.monotonic()
    client.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
    st = wait_task(client, sid, task_id, timeout=30)
    elapsed = time.monotonic() - started
    print(f"\ncancel took {elapsed:.2f}s")
    assert st["status"] == "cancelled" and elapsed < 5  # generation stopped by StoppingCriteria


def _rss_mb() -> float | None:
    """Current RSS of this (backend) process; Windows reading verified on real hardware (see app/core/procmem.py)."""
    return current_rss_mb()


def test_backend_memory_stays_low_across_repeated_transcriptions(client):
    """§5.4: models are released after each task. They run in a worker process that exits, so the backend
    process never holds model memory and does not grow from one transcription to the next."""
    if _rss_mb() is None:
        pytest.skip("current RSS not measurable on this platform without extra packages")
    readings: list[float] = []
    for _ in range(2):
        run(client, SPEECH / "zh16.wav")
        readings.append(_rss_mb() or 0.0)
    print(f"\nbackend RSS after each transcription: {[f'{r:.0f} MB' for r in readings]}")
    assert "torch" not in sys.modules, "models must never be loaded in the backend process"
    assert readings[-1] < 1500 and readings[-1] - readings[0] < 200
