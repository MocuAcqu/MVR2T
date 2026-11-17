"""YouTube 連結（yt-dlp）：網址檢查、字幕轉逐字稿、元件安裝與更新、讀取資訊與下載（用假的 yt-dlp）。"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.engines.media import ffmpeg as ff
from app.main import create_app
from app.models import ytdlp
from app.models.ytdlp import Release, YtDlpComponent, YtDlpError, parse_sums, resolve_latest
from app.services import youtube as yt

FAKE = Path(__file__).parent / "fixtures" / "fake_ytdlp.py"
LOC = ff.locate_ffmpeg("", Path("/nonexistent"))
needs_ffmpeg = pytest.mark.skipif(LOC is None, reason="FFmpeg / ffprobe not installed")


# ---------------------------------------------------------------------------
# 網址、字幕、錯誤訊息
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "vid"),
    [
        ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "jNQXAC9IVRw"),
        ("youtube.com/watch?v=jNQXAC9IVRw&list=PLx&index=2", "jNQXAC9IVRw"),
        ("https://youtu.be/jNQXAC9IVRw?t=10", "jNQXAC9IVRw"),
        ("https://m.youtube.com/shorts/jNQXAC9IVRw", "jNQXAC9IVRw"),
        ("https://www.youtube.com/playlist?list=PLx", None),
        ("https://evil.example/watch?v=jNQXAC9IVRw", None),
        ("https://www.youtube.com/watch?v=short", None),
        ("", None),
    ],
)
def test_only_single_youtube_videos_are_accepted(text, vid):
    assert yt.parse_video_id(text) == vid


def test_the_url_given_to_yt_dlp_is_rebuilt_from_the_video_id():
    assert yt.canonical_url("youtu.be/jNQXAC9IVRw?list=PLx")[1] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    with pytest.raises(yt.MediaError):
        yt.canonical_url("https://www.youtube.com/watch?v=jNQXAC9IVRw\nhttps://evil.example")


def test_vtt_cues_are_cleaned_and_repeats_merged():
    cues = yt.parse_vtt(
        "﻿WEBVTT\nKind: captions\n\n1\n00:00:01.000 --> 00:00:02.000 align:start\n<c.colorE5E5E5>Hello</c> &amp; hi\n\n"
        "00:00:02.000 --> 00:00:03.000\nHello &amp; hi\n\n00:00:04.000 --> 00:00:03.000\nbad\n\n1:00:00.500 --> 1:00:01.250\ntwo\nlines\n"
    )
    assert cues == [{"start": 1.0, "end": 3.0, "text": "Hello & hi"}, {"start": 3600.5, "end": 3601.25, "text": "two lines"}]


def test_chinese_subtitles_become_a_traditional_chinese_transcript():
    t = yt.subtitle_transcript("m1", "zh-Hans", "中文（简体）", [{"start": 0.0, "end": 1.0, "text": "软件测试与开会"}], 1.0)
    assert t["source"] == "subtitles" and t["language"] == "Chinese" and t["timing"] == "aligned"
    assert t["segments"][0]["text"] == "軟體測試與開會" and t["segments"][0]["words"] == []
    assert yt.language_name("en-US") == "English" and yt.language_name("zh-HK") == "Cantonese" and yt.language_name("fr") == "fr"


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("ERROR: [youtube] x: Private video. Sign in", "私人影片"),
        ("ERROR: [youtube] x: Sign in to confirm your age.", "年齡限制"),
        ("ERROR: [youtube] x: Sign in to confirm you're not a bot.", "更新 YouTube 下載元件"),
        ("WARNING: x\nERROR: [youtube] x: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "無法連線到 YouTube"),
        ("ERROR: something new", "something new"),
    ],
)
def test_yt_dlp_errors_are_explained(stderr, expected):
    assert expected in yt.friendly_error(stderr)


# ---------------------------------------------------------------------------
# 元件：查詢最新版、安裝、更新、刪除
# ---------------------------------------------------------------------------

EXE = b"#!fake yt-dlp\n" * 100


def release_json(version: str, url: str, data: bytes, digest: str | None = None) -> bytes:
    return json.dumps({
        "tag_name": version,
        "published_at": "2026-11-10T00:00:00Z",
        "assets": [
            {"name": ytdlp.asset_name(), "size": len(data), "browser_download_url": url + "/exe", "digest": digest},
            {"name": "SHA2-256SUMS", "size": 100, "browser_download_url": url + "/sums"},
        ],
    }).encode()


def test_latest_release_is_verified_against_its_checksum_file():
    sha = hashlib.sha256(EXE).hexdigest()
    sums = f"{'0' * 64}  yt-dlp.tar.gz\n{sha}  {ytdlp.asset_name()}\n".encode()
    pages = {ytdlp.LATEST_URL: release_json("2026.11.10", "https://x", EXE, f"sha256:{sha}"), "https://x/sums": sums}
    rel = resolve_latest(pages.__getitem__)
    assert (rel.version, rel.size, rel.sha256, rel.url) == ("2026.11.10", len(EXE), sha, "https://x/exe")
    pages[ytdlp.LATEST_URL] = release_json("2026.11.10", "https://x", EXE, "sha256:" + "f" * 64)
    with pytest.raises(YtDlpError):
        resolve_latest(pages.__getitem__)
    assert parse_sums(f"{sha} *a.exe\n") == {"a.exe": sha}


def test_asset_names_per_platform():
    assert ytdlp.asset_name("win32", "AMD64") == "yt-dlp.exe"
    assert ytdlp.asset_name("darwin", "arm64") == "yt-dlp_macos"
    assert ytdlp.asset_name("linux", "x86_64") == "yt-dlp_linux"


def test_install_update_and_delete(tmp_path):
    from tests.test_model_manager import Server

    server = Server()
    try:
        server.files["/v1"] = EXE
        server.files["/v2"] = EXE + b"v2"
        current = {"rel": Release("2026.11.01", ytdlp.asset_name() or "", server.url + "/v1", len(EXE), hashlib.sha256(EXE).hexdigest())}
        comp = YtDlpComponent(tmp_path / "runtime", resolver=lambda: current["rel"])
        assert comp.snapshot()["installed"] is False

        comp.install()
        comp.wait()
        s = comp.snapshot()
        assert s["installed"] and s["version"] == "2026.11.01" and s["last"]["ok"], s
        assert comp.executable() == comp.exe and comp.exe.read_bytes() == EXE

        # a newer release appears: "check" reports it, "install" updates in place
        v2 = EXE + b"v2"
        current["rel"] = Release("2026.11.14", ytdlp.asset_name() or "", server.url + "/v2", len(v2), hashlib.sha256(v2).hexdigest())
        comp.check()
        comp.wait()
        assert comp.snapshot()["update_available"] is True
        comp.install()
        comp.wait()
        s = comp.snapshot()
        assert s["version"] == "2026.11.14" and not s["update_available"] and comp.exe.read_bytes() == v2

        # a tampered download is rejected and the installed version is kept
        current["rel"] = Release("2026.11.15", ytdlp.asset_name() or "", server.url + "/v1", len(EXE), "0" * 64)
        comp.install()
        comp.wait()
        s = comp.snapshot()
        assert not s["last"]["ok"] and "雜湊" in s["last"]["message"] and s["version"] == "2026.11.14"

        with pytest.raises(YtDlpError):
            comp.delete(in_use=lambda: True)
        comp.delete()
        assert comp.snapshot()["installed"] is False and not comp.dir.exists()
    finally:
        server.httpd.shutdown()


# ---------------------------------------------------------------------------
# API：讀取資訊、下載（假的 yt-dlp）
# ---------------------------------------------------------------------------


def _tone(path: Path, seconds: float = 3.0) -> None:
    rate = 16000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate))))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "ytdlp_argv", lambda exe: [sys.executable, str(FAKE)])
    wav = tmp_path / "source.wav"
    _tone(wav)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_YTDLP_WAV", str(wav))
    monkeypatch.setenv("FAKE_YTDLP_LOG", str(log))
    cfg = Settings(auth_token="", data_dir=tmp_path / "data", js_runtime=str(tmp_path / "electron.exe"))
    app = create_app(cfg)
    comp: YtDlpComponent = app.state.ytdlp
    comp.dir.mkdir(parents=True)
    comp.exe.write_bytes(b"x")
    (comp.dir / ytdlp.INFO_FILE).write_text(json.dumps({"version": "2026.11.14"}), encoding="utf-8")
    with TestClient(app) as client:
        sid = client.post("/api/session").json()["session_id"]
        yield client, sid, log


def _wait(client, sid, task_id, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        t = client.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()
        if t["status"] in ("completed", "failed", "cancelled"):
            return t
        time.sleep(0.1)
    raise AssertionError("task did not finish")


def test_component_must_be_installed_first(tmp_path):
    app = create_app(Settings(auth_token="", data_dir=tmp_path / "data"))
    with TestClient(app) as client:
        sid = client.post("/api/session").json()["session_id"]
        r = client.post("/api/youtube/probe", json={"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw"})
        assert r.status_code == 412 and "模型管理" in r.json()["detail"]
        assert client.get("/api/youtube/component").json()["installed"] is False


def test_probe_returns_title_duration_and_uploaded_subtitles(api):
    client, sid, log = api
    r = client.post("/api/youtube/probe", json={"session_id": sid, "url": "youtu.be/jNQXAC9IVRw?list=PLx"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["title"] == "我的 第一支/影片" and v["channel"] == "Mocu" and v["duration"] == 3.0
    assert v["audio_size"] == 50000  # the m4a audio-only format
    assert v["subtitles"] == [{"lang": "zh-Hans", "name": "中文（简体）"}]  # no automatic captions, no live chat
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert call["args"][-1] == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert "--no-playlist" in call["args"] and call["electron_run_as_node"] == "1"
    assert call["args"][call["args"].index("--js-runtimes") + 1].startswith("node:")


def test_probe_reports_private_videos(api, monkeypatch):
    client, sid, _ = api
    monkeypatch.setenv("FAKE_YTDLP_MODE", "private")
    r = client.post("/api/youtube/probe", json={"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw"})
    assert r.status_code == 502 and "私人影片" in r.json()["detail"]


@needs_ffmpeg
def test_download_audio_and_use_the_uploaded_subtitles(api):
    client, sid, log = api
    body = {"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw", "title": "我的 第一支/影片", "duration": 3.0,
            "subtitle": {"lang": "zh-Hans", "name": "中文（简体）"}}
    r = client.post("/api/youtube/download", json=body)
    assert r.status_code == 200, r.text
    t = _wait(client, sid, r.json()["task_id"])
    assert t["status"] == "completed", t
    media = t["result"]["media"]
    assert media["origin"] == "youtube" and media["source_url"].endswith("v=jNQXAC9IVRw")
    assert media["filename"] == "我的 第一支 影片.wav" and media["kind"] == "audio" and 2.9 < media["duration"] < 3.1
    assert t["result"]["subtitles"] is True
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert call["args"][call["args"].index("--sub-langs") + 1] == "zh-Hans"

    tr = client.get("/api/transcript", params={"session_id": sid, "media_id": media["media_id"]})
    assert tr.status_code == 200, tr.text
    transcript = tr.json()
    assert transcript["source"] == "subtitles" and [s["text"] for s in transcript["segments"]] == ["軟體測試", "與開會"]

    # extracting audio afterwards keeps the subtitle transcript (its times follow the original video)
    r = client.post("/api/media/extract-audio", json={"session_id": sid, "media_id": media["media_id"]})
    assert _wait(client, sid, r.json()["task_id"])["status"] == "completed"
    assert client.get("/api/transcript", params={"session_id": sid, "media_id": media["media_id"]}).status_code == 200


@needs_ffmpeg
def test_download_without_subtitles_then_cancel_a_slow_one(api, monkeypatch):
    client, sid, _ = api
    r = client.post("/api/youtube/download", json={"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw", "title": "a"})
    t = _wait(client, sid, r.json()["task_id"])
    assert t["status"] == "completed" and t["result"]["subtitles"] is False

    monkeypatch.setenv("FAKE_YTDLP_MODE", "slow")
    r = client.post("/api/youtube/download", json={"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw", "title": "b"})
    task_id = r.json()["task_id"]
    deadline = time.monotonic() + 10
    while client.get(f"/api/tasks/{task_id}", params={"session_id": sid}).json()["stage"] != "正在下載音訊":
        assert time.monotonic() < deadline
        time.sleep(0.1)
    started = time.monotonic()
    client.post(f"/api/tasks/{task_id}/cancel", params={"session_id": sid})
    t = _wait(client, sid, task_id)
    assert t["status"] == "cancelled" and time.monotonic() - started < 5
    session_dir = client.app.state.sessions.get(sid).dir
    assert not any((session_dir / "media").iterdir())  # nothing left behind (the first download was replaced too)


def test_download_rejects_bad_urls_and_subtitle_languages(api):
    client, sid, _ = api
    r = client.post("/api/youtube/download", json={"session_id": sid, "url": "https://example.com/x"})
    assert r.status_code == 422
    r = client.post("/api/youtube/download", json={"session_id": sid, "url": "https://youtu.be/jNQXAC9IVRw", "subtitle": {"lang": "../x", "name": "x"}})
    assert r.status_code == 422
