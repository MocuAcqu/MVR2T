"""Phase 04 acceptance tests against REAL FFmpeg (skipped when FFmpeg is not installed).

Acceptance (PROJECT_SPEC Phase 04):
- the specified formats can be processed;
- time offsets are preserved for different audio lengths.

The offset test plants short 2 kHz "markers" at known times in the source audio, runs the full
upload -> extract -> segment pipeline, then finds each marker inside the segment files and checks that
segment.start + local_position == original time.
"""
from __future__ import annotations

import math
import struct
import subprocess
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.engines.media import ffmpeg as ff
from app.main import create_app

LOC = ff.locate_ffmpeg("", Path("/nonexistent"))
pytestmark = pytest.mark.skipif(LOC is None, reason="FFmpeg / ffprobe not installed")

RATE = 16000
MARKER_SECONDS = 0.03


# ---------------------------------------------------------------------------
# media generation
# ---------------------------------------------------------------------------


def write_signal_wav(path: Path, duration: float, silences: list[tuple[float, float]], markers: list[float]) -> None:
    """440 Hz tone (amplitude 0.25) with silent gaps, plus loud 2 kHz markers (amplitude 0.6) at given times."""
    n = int(duration * RATE)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        v = 0.0 if any(s <= t < e for s, e in silences) else 0.25 * math.sin(2 * math.pi * 440 * t)
        if any(m <= t < m + MARKER_SECONDS for m in markers):
            v += 0.6 * math.sin(2 * math.pi * 2000 * (t - math.floor(t * 2000) / 2000) + math.pi / 2)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


ENCODE: dict[str, list[str]] = {
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
    "m4a": ["-c:a", "aac", "-b:a", "128k"],
    "aac": ["-c:a", "aac", "-b:a", "128k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "4"],
    # video containers get a tiny video track
    "mp4": ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
    "mov": ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
    "mkv": ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"],
    "webm": ["-c:v", "libvpx", "-deadline", "realtime", "-c:a", "libopus", "-shortest"],
}
VIDEO = {"mp4", "mov", "mkv", "webm"}


def encode(src_wav: Path, ext: str, out: Path) -> Path:
    args = [str(LOC.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if ext in VIDEO:
        # Give the video source the SAME length as the audio. Relying on -shortest with an infinite source
        # overshoots by a timing-dependent amount (seen as an intermittent webm duration failure on
        # Windows with FFmpeg 7.1.1).
        with wave.open(str(src_wav)) as w:
            seconds = w.getnframes() / w.getframerate()
        args += ["-f", "lavfi", "-i", f"color=c=black:s=160x120:r=10:d={seconds:.3f}"]
    args += ["-i", str(src_wav)]
    if ext in VIDEO:
        args += ["-map", "0:v", "-map", "1:a"]
    args += [*ENCODE[ext], str(out)]
    subprocess.run(args, check=True, stdin=subprocess.DEVNULL)
    return out


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="module")
def short_wav(media_dir) -> Path:
    p = media_dir / "short.wav"
    write_signal_wav(p, 6.0, [], [1.0])
    return p


# offset scenario 1: natural pauses -> cuts at silences
SIL_DURATION = 95.0
SIL_GAPS = [(27.5, 28.5), (58.0, 59.2), (86.0, 87.0)]
SIL_MARKERS = [3.0, 26.0, 31.25, 47.5, 61.0, 89.5]

# offset scenario 2: continuous audio -> hard cuts with 1 s overlap; 29.5 lies inside an overlap
HARD_DURATION = 100.0
HARD_MARKERS = [2.0, 29.5, 45.0, 75.25, 95.0]


@pytest.fixture(scope="module")
def silence_wav(media_dir) -> Path:
    p = media_dir / "silences.wav"
    write_signal_wav(p, SIL_DURATION, SIL_GAPS, SIL_MARKERS)
    return p


@pytest.fixture(scope="module")
def continuous_wav(media_dir) -> Path:
    p = media_dir / "continuous.wav"
    write_signal_wav(p, HARD_DURATION, [], HARD_MARKERS)
    return p


# ---------------------------------------------------------------------------
# client helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def data_dir(tmp_path) -> Path:
    return tmp_path / "userData"


@pytest.fixture()
def client(data_dir):
    app = create_app(Settings(auth_token="", data_dir=data_dir))  # FFmpeg auto-discovery, like the real app
    with TestClient(app) as c:
        yield c


def new_session(client) -> str:
    r = client.post("/api/session")
    assert r.status_code == 200
    return r.json()["session_id"]


def upload(client, sid: str, path: Path, filename: str | None = None):
    return client.post(
        "/api/media/upload",
        params={"session_id": sid, "filename": filename or path.name},
        content=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )


def wait_task(client, sid: str, task_id: str, timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
        if state["status"] in ("completed", "failed", "cancelled"):
            return state
        time.sleep(0.05)
    raise AssertionError("task did not finish")


def extract(client, sid: str, media_id: str) -> dict:
    r = client.post("/api/media/extract-audio", json={"session_id": sid, "media_id": media_id})
    assert r.status_code == 200, r.text
    state = wait_task(client, sid, r.json()["task_id"])
    assert state["status"] == "completed", state
    return state["result"]


def session_dir(data_dir: Path, sid: str) -> Path:
    return data_dir / "temp" / "sessions" / sid


def marker_onsets(path: Path, threshold: float = 0.5) -> list[float]:
    """Local times (s) where a marker starts in a 16 kHz mono WAV."""
    with wave.open(str(path), "rb") as w:
        assert (w.getframerate(), w.getnchannels()) == (RATE, 1)
        raw = w.readframes(w.getnframes())
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    limit = threshold * 32767
    onsets, last = [], -1.0
    for i, s in enumerate(samples):
        if abs(s) > limit:
            t = i / RATE
            if t - last > 0.5:  # a new marker
                onsets.append(t)
            last = t
    return onsets


def global_marker_times(data_dir: Path, sid: str, media_id: str, result: dict) -> list[float]:
    seg_dir = session_dir(data_dir, sid) / "media" / media_id / "audio" / "segments"
    found = []
    for seg in result["segments"]:
        for local in marker_onsets(seg_dir / f"seg_{seg['index']:04d}.wav"):
            found.append(round(seg["start"] + local, 3))
    return found


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", sorted(ENCODE))
def test_every_supported_format_imports_and_extracts(client, data_dir, short_wav, media_dir, ext):
    src = encode(short_wav, ext, media_dir / f"fmt_short.{ext}")
    sid = new_session(client)
    r = upload(client, sid, src, f"我的檔案 {ext}.{ext.upper()}")  # unicode + upper-case extension
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["format"] == ext and info["kind"] == ("video" if ext in VIDEO else "audio")
    assert info["filename"] == f"我的檔案 {ext}.{ext.upper()}"
    assert info["size"] == src.stat().st_size
    assert info["duration"] == pytest.approx(6.0, abs=0.15)
    assert info["has_video"] is (ext in VIDEO)

    result = extract(client, sid, info["media_id"])
    assert result["sample_rate"] == 16000 and result["channels"] == 1
    assert result["duration"] == pytest.approx(6.0, abs=0.15)
    assert len(result["segments"]) == 1
    # stored under a server-chosen name, never the user's file name
    assert (session_dir(data_dir, sid) / "media" / info["media_id"] / f"original.{ext}").is_file()


@pytest.mark.parametrize("ext", ["wav", "flac", "mp3", "m4a", "mp4", "webm"])
def test_offsets_preserved_when_cutting_at_silences(client, data_dir, silence_wav, media_dir, ext):
    src = silence_wav if ext == "wav" else encode(silence_wav, ext, media_dir / f"fmt_silences.{ext}")
    sid = new_session(client)
    info = upload(client, sid, src).json()
    result = extract(client, sid, info["media_id"])

    segs = result["segments"]
    assert [s["boundary"] for s in segs] == ["silence", "silence", "end"]
    # cut points are inside the planted pauses, so no marker / sentence is split
    for s in segs[:-1]:
        assert any(a <= s["end"] <= b for a, b in SIL_GAPS), s
    # lossless formats are sample exact; lossy codecs smear the onset by a few ms
    tol = 0.003 if ext in ("wav", "flac") else 0.03
    found = global_marker_times(data_dir, sid, info["media_id"], result)
    assert len(found) == len(SIL_MARKERS), found
    for expected, got in zip(SIL_MARKERS, found):
        assert got == pytest.approx(expected, abs=tol), (expected, got)


def test_offsets_preserved_with_hard_cuts_and_overlap(client, data_dir, continuous_wav):
    sid = new_session(client)
    info = upload(client, sid, continuous_wav).json()
    result = extract(client, sid, info["media_id"])
    segs = result["segments"]
    assert [(s["start"], s["end"]) for s in segs] == [(0.0, 30.0), (29.0, 59.0), (58.0, 88.0), (87.0, 100.0)]
    found = global_marker_times(data_dir, sid, info["media_id"], result)
    # 29.5 is inside the overlap of segments 0 and 1 -> found twice, both mapping to the same original time
    assert sorted(found) == pytest.approx(sorted(HARD_MARKERS + [29.5]), abs=0.003)


def test_long_audio_30_minutes(client, data_dir):
    """30 min of audio with a 0.8 s pause every 37 s: offsets continuous, every segment within bounds."""
    src = data_dir.parent / "long.flac"
    subprocess.run(
        [str(LOC.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-f", "lavfi", "-i", "sine=f=440:r=16000:d=1800",
         "-af", r"volume=volume=0:enable='lt(mod(t\,37)\,0.8)'", "-c:a", "flac", str(src)],
        check=True, stdin=subprocess.DEVNULL,
    )
    sid = new_session(client)
    info = upload(client, sid, src).json()
    assert info["duration"] == pytest.approx(1800, abs=0.1)
    started = time.monotonic()
    result = extract(client, sid, info["media_id"])
    elapsed = time.monotonic() - started
    segs = result["segments"]
    assert segs[0]["start"] == 0 and segs[-1]["end"] == pytest.approx(1800, abs=0.05)
    for a, b in zip(segs, segs[1:]):
        assert b["start"] <= a["end"] and b["start"] > a["start"]
    assert all(5 <= s["duration"] <= 38 for s in segs)
    assert sum(s["boundary"] == "silence" for s in segs) >= len(segs) - 2
    print(f"\n30 min audio: {len(segs)} segments, extraction {elapsed:.1f}s")


def test_unsupported_format_rejected(client, data_dir, tmp_path):
    sid = new_session(client)
    p = tmp_path / "notes.pdf"
    p.write_bytes(b"%PDF-1.4 hello")
    r = upload(client, sid, p)
    assert r.status_code == 415
    assert not (session_dir(data_dir, sid) / "media").exists() or not any((session_dir(data_dir, sid) / "media").iterdir())


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"\x00\x01garbage" * 1000, "損壞"), (b"ftypisom" + b"\x00" * 2000, "損壞")],
)
def test_corrupt_file_rejected_and_cleaned_up(client, data_dir, tmp_path, content, message):
    sid = new_session(client)
    p = tmp_path / "broken.mp4"
    p.write_bytes(content)
    r = upload(client, sid, p)
    assert r.status_code == 422 and message in r.json()["detail"]
    assert not any((session_dir(data_dir, sid) / "media").iterdir())


def test_video_without_audio_rejected(client, media_dir, tmp_path):
    p = tmp_path / "silent.mp4"
    subprocess.run(
        [str(LOC.ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi",
         "-i", "color=c=black:s=160x120:r=10:d=2", "-c:v", "libx264", "-preset", "ultrafast", str(p)],
        check=True, stdin=subprocess.DEVNULL,
    )
    sid = new_session(client)
    r = upload(client, sid, p)
    assert r.status_code == 422 and "沒有音訊軌" in r.json()["detail"]


def test_size_limit_enforced(data_dir, short_wav):
    app = create_app(Settings(auth_token="", data_dir=data_dir, max_upload_bytes=1000))
    with TestClient(app) as c:
        sid = new_session(c)
        r = upload(c, sid, short_wav)
        assert r.status_code == 413


def test_path_traversal_filename_is_harmless(client, data_dir, short_wav):
    sid = new_session(client)
    r = upload(client, sid, short_wav, "../../../evil.wav")
    assert r.status_code == 200
    info = r.json()
    assert info["filename"] == "evil.wav"
    assert (session_dir(data_dir, sid) / "media" / info["media_id"] / "original.wav").is_file()
    assert not (data_dir / "evil.wav").exists() and not (data_dir.parent / "evil.wav").exists()


def test_missing_ffmpeg_gives_clear_error(client, short_wav, monkeypatch):
    monkeypatch.setattr(ff, "locate_ffmpeg", lambda *a, **k: None)
    sid = new_session(client)
    r = upload(client, sid, short_wav)
    assert r.status_code == 503 and "FFmpeg" in r.json()["detail"]
    assert client.get("/api/system/ffmpeg").json()["available"] is False


def test_ffmpeg_status_reports_version(client):
    st = client.get("/api/system/ffmpeg").json()
    assert st["available"] is True and st["version"] and st["source"] in ("path", "winget", "app-runtime")


def test_cancel_extraction_stops_ffmpeg_and_cleans_up(client, data_dir, silence_wav, monkeypatch):
    # -re makes FFmpeg read at real-time speed, so the 95 s file takes ~95 s and we can cancel mid-way.
    original = ff.build_extract_args

    def slow(ffmpeg, src, dst):
        args = original(ffmpeg, src, dst)
        i = args.index("-i")
        return args[:i] + ["-re"] + args[i:]

    monkeypatch.setattr(ff, "build_extract_args", slow)
    sid = new_session(client)
    info = upload(client, sid, silence_wav).json()
    task_id = client.post("/api/media/extract-audio", json={"session_id": sid, "media_id": info["media_id"]}).json()["task_id"]

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        st = client.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
        if st["progress"] > 0.005:
            break
        time.sleep(0.1)
    assert st["status"] == "running" and 0 < st["progress"] < 0.5

    # a second extraction for the same media is refused while one is running
    dup = client.post("/api/media/extract-audio", json={"session_id": sid, "media_id": info["media_id"]})
    assert dup.status_code == 409

    started = time.monotonic()
    client.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
    st = wait_task(client, sid, task_id, timeout=10)
    assert st["status"] == "cancelled"
    assert time.monotonic() - started < 3  # FFmpeg was killed, not waited for
    assert not (session_dir(data_dir, sid) / "media" / info["media_id"] / "audio").exists()


def test_new_session_and_end_session_delete_temp_files(client, data_dir, short_wav):
    sid1 = new_session(client)
    upload(client, sid1, short_wav)
    assert session_dir(data_dir, sid1).exists()
    sid2 = new_session(client)  # e.g. the user reloaded the window
    assert not session_dir(data_dir, sid1).exists()
    assert client.get("/api/tasks/x", params={"session_id": sid1}).status_code == 404
    assert client.delete(f"/api/session/{sid2}").status_code == 204
    assert not session_dir(data_dir, sid2).exists()


def test_replacing_media_removes_previous_files(client, data_dir, short_wav):
    sid = new_session(client)
    first = upload(client, sid, short_wav).json()
    extract(client, sid, first["media_id"])
    second = upload(client, sid, short_wav).json()
    media_root = session_dir(data_dir, sid) / "media"
    assert sorted(p.name for p in media_root.iterdir()) == [second["media_id"]]
    r = client.post("/api/media/extract-audio", json={"session_id": sid, "media_id": first["media_id"]})
    assert r.status_code == 404


def test_stale_sessions_removed_on_startup(data_dir):
    stale = data_dir / "temp" / "sessions" / "leftover-from-crash"
    stale.mkdir(parents=True)
    (stale / "audio.wav").write_bytes(b"x")
    outside = data_dir / "models" / "keep.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"model")
    with TestClient(create_app(Settings(auth_token="", data_dir=data_dir))):
        assert not stale.exists()
    assert outside.exists()  # models and anything outside temp/sessions are never touched


def test_session_temp_removed_on_shutdown(data_dir, short_wav):
    with TestClient(create_app(Settings(auth_token="", data_dir=data_dir))) as c:
        sid = new_session(c)
        upload(c, sid, short_wav)
        assert session_dir(data_dir, sid).exists()
    assert not session_dir(data_dir, sid).exists()
