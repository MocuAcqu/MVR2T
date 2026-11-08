"""Phase 04 unit tests: FFmpeg output parsing, FFmpeg discovery and the segment planner (no FFmpeg needed)."""
from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest

from app.engines.media import ffmpeg as ff
from app.engines.media.segmenter import SegmentParams, plan_segments, write_segments

# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def test_parse_version():
    assert ff.parse_version("ffmpeg version 7.1-full_build-www.gyan.dev Copyright (c)") == "7.1-full_build-www.gyan.dev"
    assert ff.parse_version("ffmpeg version n6.1.1 Copyright") == "n6.1.1"
    assert ff.parse_version("garbage") is None


def _probe_json(streams, fmt=None):
    return json.dumps({"streams": streams, "format": fmt if fmt is not None else {"format_name": "mov,mp4", "duration": "12.5"}})


def test_parse_probe_video_with_audio():
    p = ff.parse_probe(_probe_json([
        {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
    ]))
    assert (p.duration, p.has_video, p.audio_codec, p.sample_rate, p.channels, p.width) == (12.5, True, "aac", 48000, 2, 1280)


def test_parse_probe_audio_with_cover_art_is_not_video():
    p = ff.parse_probe(_probe_json([
        {"codec_type": "audio", "codec_name": "mp3", "sample_rate": "44100", "channels": 2},
        {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
    ]))
    assert p.has_video is False


def test_parse_probe_duration_falls_back_to_stream():
    p = ff.parse_probe(_probe_json([{"codec_type": "audio", "duration": "3.25"}], {"format_name": "wav"}))
    assert p.duration == 3.25


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        ("not json", "損壞"),
        (_probe_json([], {}), "無法辨識"),
        (_probe_json([{"codec_type": "video", "codec_name": "h264"}]), "沒有音訊軌"),
        (_probe_json([{"codec_type": "audio"}], {"format_name": "x", "duration": "N/A"}), "長度"),
    ],
)
def test_parse_probe_errors(stdout, message):
    with pytest.raises(ff.ProbeError, match=message):
        ff.parse_probe(stdout)


def test_parse_progress_seconds():
    assert ff.parse_progress_seconds("out_time_us=1500000") == 1.5
    assert ff.parse_progress_seconds("out_time_ms=2000000\n") == 2.0  # ffmpeg's *_ms is really microseconds
    assert ff.parse_progress_seconds("out_time=00:00:01.50") is None
    assert ff.parse_progress_seconds("progress=continue") is None


def test_parse_silences():
    lines = [
        "[silencedetect @ 0x1] silence_start: 1.5",
        "[silencedetect @ 0x1] silence_end: 2.25 | silence_duration: 0.75",
        "size=N/A time=00:00:05",
        "[silencedetect @ 0x1] silence_start: -0.01",  # clamped to 0
        "[silencedetect @ 0x1] silence_end: 0.4 | silence_duration: 0.41",
        "[silencedetect @ 0x1] silence_start: 9.5",  # never ends -> closed at total duration
    ]
    assert ff.parse_silences(lines, 10.0) == [(1.5, 2.25), (0.0, 0.4), (9.5, 10.0)]


def test_extract_args_are_safe_and_complete(tmp_path):
    src = tmp_path / "a b; rm -rf" / "original.mp4"
    args = ff.build_extract_args(Path("ffmpeg"), src, tmp_path / "out.wav")
    assert isinstance(args, list) and str(src) in args  # path is ONE argument, never shell-parsed
    for flag in ("-nostdin", "-vn", "-progress"):
        assert flag in args
    assert args[args.index("-ar") + 1] == "16000" and args[args.index("-ac") + 1] == "1"
    assert args[args.index("-c:a") + 1] == "pcm_s16le"


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def _fake_pair(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        (d / f"{name}{ff.EXE_SUFFIX}").write_text("")


def test_locate_prefers_settings_then_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(ff.shutil, "which", lambda name: None)
    monkeypatch.setattr(ff, "_winget_candidates", lambda: [])  # ignore a real winget install on this machine
    custom, runtime = tmp_path / "custom", tmp_path / "runtime"
    assert ff.locate_ffmpeg("", runtime) is None
    _fake_pair(runtime / "bin")
    assert ff.locate_ffmpeg("", runtime).source == "app-runtime"
    _fake_pair(custom)
    loc = ff.locate_ffmpeg(str(custom), runtime)
    assert loc.source == "settings" and loc.ffmpeg.parent == custom


def test_locate_requires_both_binaries_from_same_place(tmp_path, monkeypatch):
    monkeypatch.setattr(ff.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    monkeypatch.setattr(ff, "_winget_candidates", lambda: [])  # ignore a real winget install on this machine
    half = tmp_path / "half"
    half.mkdir()
    (half / f"ffmpeg{ff.EXE_SUFFIX}").write_text("")
    assert ff.locate_ffmpeg(str(half), tmp_path / "none") is None


def test_locate_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(ff.shutil, "which", lambda name: f"/opt/bin/{name}")
    loc = ff.locate_ffmpeg("", tmp_path / "none")
    assert loc.source == "path" and loc.ffprobe == Path("/opt/bin/ffprobe")


# ---------------------------------------------------------------------------
# segment planning
# ---------------------------------------------------------------------------

P = SegmentParams(target_seconds=30, window_seconds=8, min_seconds=5, overlap_seconds=1)


def _assert_covers(plans, duration):
    assert plans[0].start == 0 and plans[-1].end == pytest.approx(duration)
    for a, b in zip(plans, plans[1:]):
        assert b.start <= a.end  # contiguous or overlapping, never a gap
        assert b.start > a.start
    assert [p.index for p in plans] == list(range(len(plans)))


def test_short_audio_is_one_segment():
    plans = plan_segments(37.9, [], P)
    assert len(plans) == 1 and plans[0].boundary == "end"


def test_cuts_at_silence_midpoint_and_prefers_longest_silence():
    silences = [(24.0, 24.4), (31.0, 32.0), (35.0, 35.3)]  # longest is 31-32 -> cut at 31.5
    plans = plan_segments(80, silences, P)
    assert plans[0].end == 31.5 and plans[0].boundary == "silence"
    assert plans[1].start == 31.5  # no overlap after a silence cut
    _assert_covers(plans, 80)


def test_hard_cut_with_overlap_when_no_silence():
    plans = plan_segments(100, [], P)
    assert [(p.start, p.end, p.boundary) for p in plans] == [
        (0.0, 30.0, "hard"), (29.0, 59.0, "hard"), (58.0, 88.0, "hard"), (87.0, 100.0, "end"),
    ]


def test_silence_outside_window_is_ignored():
    plans = plan_segments(100, [(10.0, 11.0), (45.0, 46.0)], P)
    assert plans[0].boundary == "hard" and plans[0].end == 30.0


def test_long_audio_plan_stays_reasonable():
    duration = 3600.0
    silences = [(t, t + 0.6) for t in range(20, 3600, 23)]
    plans = plan_segments(duration, silences, P)
    _assert_covers(plans, duration)
    assert all(P.min_seconds <= p.duration <= P.target_seconds + P.window_seconds for p in plans)


def test_write_segments_is_sample_accurate(tmp_path):
    rate, n = 16000, 16000 * 10
    src = tmp_path / "a.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", i % 30000) for i in range(n)))
    plans = plan_segments(10.0, [], SegmentParams(target_seconds=3, window_seconds=1, min_seconds=1, overlap_seconds=0.5))
    paths = write_segments(src, plans, tmp_path / "segs")
    for plan, path in zip(plans, paths):
        with wave.open(str(path), "rb") as w:
            assert w.getnframes() == round(plan.end * rate) - round(plan.start * rate)
            first = struct.unpack("<h", w.readframes(1))[0]
            assert first == round(plan.start * rate) % 30000  # first sample is exactly the original sample at `start`
