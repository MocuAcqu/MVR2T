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
from app.main import create_app
from app.models.registry import QWEN3_ASR_0_6B, QWEN3_FORCED_ALIGNER_0_6B
from app.models.store import is_installed
from tests.test_media_api import LOC, extract, new_session, upload, wait_task

SPEECH = Path(os.environ.get("MVR2T_TEST_SPEECH_DIR", "/nonexistent"))
MODELS_DATA = Path(os.environ.get("MVR2T_DATA_DIR") or default_user_data_dir())

try:
    import torch  # noqa: F401
    import transformers  # noqa: F401

    HAVE_TORCH = True
except ImportError:  # pragma: no cover
    HAVE_TORCH = False

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
    # models from the real userData folder, session temp in a throwaway folder
    cfg = Settings(auth_token="", data_dir=tmp_path / "userData")
    object.__setattr__(cfg, "data_dir", tmp_path / "userData")
    app = create_app(cfg)
    real_models = MODELS_DATA / "models"

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
    # the "model installed" check in start_transcription looks at cfg.models_root
    (tmp_path / "userData").mkdir(parents=True)
    (tmp_path / "userData" / "models").symlink_to(real_models, target_is_directory=True)
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


def _windows_rss_mb() -> float:
    """Current working set of this process (same meaning as Linux VmRSS). `resource` does not exist on Windows."""
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.WorkingSetSize / 1024**2


def _rss_mb() -> float:
    if sys.platform == "win32":
        return _windows_rss_mb()
    try:
        with open("/proc/self/status") as f:
            return next(int(line.split()[1]) / 1024 for line in f if line.startswith("VmRSS"))
    except OSError:  # pragma: no cover - non-Linux (macOS)
        import resource  # Unix only; imported here so this module still loads on Windows

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def test_backend_memory_stays_low_across_repeated_transcriptions(client):
    """§5.4: models are released after each task. They run in a worker process that exits, so the backend
    process never holds model memory and does not grow from one transcription to the next."""
    readings = []
    for _ in range(2):
        run(client, SPEECH / "zh16.wav")
        readings.append(_rss_mb())
    print(f"\nbackend RSS after each transcription: {[f'{r:.0f} MB' for r in readings]}")
    assert "torch" not in sys.modules or readings[-1] < 1500
    assert readings[-1] < 1500 and readings[-1] - readings[0] < 200
