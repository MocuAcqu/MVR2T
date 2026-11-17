"""逐字稿編輯器（規格 §2.1-D）、工作區播放器、設定頁（規格 §12.4）的 API。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.session.manager import MediaRecord

SEGMENTS = [
    {"id": 0, "start": 0.0, "end": 2.0, "text": "大家好", "timing": "aligned", "words": [{"text": "大家好", "start": 0.0, "end": 2.0}]},
    {"id": 1, "start": 2.0, "end": 4.0, "text": "今天開會", "timing": "aligned", "words": []},
    {"id": 2, "start": 4.0, "end": 6.0, "text": "謝謝", "timing": "estimated", "words": []},
]


def _media(session, tmp_path: Path, transcript: bool = True) -> MediaRecord:
    d = session.dir / "media" / "m1"
    (d / "audio").mkdir(parents=True)
    original = d / "original.mp3"
    original.write_bytes(bytes(range(256)) * 40)  # 10,240 bytes
    rec = MediaRecord("m1", "會議.mp3", "mp3", "audio", original.stat().st_size, original, {"duration": 6.0})
    if transcript:
        rec.transcript = {"media_id": "m1", "language": "Chinese", "timing": "mixed", "duration": 6.0, "models": {}, "warnings": [], "segments": SEGMENTS}
    session.media = rec
    return rec


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(auth_token="", data_dir=tmp_path / "data"))
    with TestClient(app) as c:
        sid = c.post("/api/session").json()["session_id"]
        yield c, sid, app.state.sessions.get(sid)


def test_edit_delete_and_merge_sentences(client, tmp_path):
    c, sid, session = client
    rec = _media(session, tmp_path)
    merged = {"id": 0, "start": 0.0, "end": 4.0, "text": "大家好，今天開會", "timing": "aligned", "words": SEGMENTS[0]["words"]}
    body = {"session_id": sid, "media_id": "m1", "segments": [merged, {**SEGMENTS[2], "text": "  "}]}  # merge 0+1, empty text = delete
    # keep sentence 2 but edit it in a second request below
    r = c.put("/api/transcript", json=body)
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["edited"] is True and [(s["id"], s["text"], s["end"]) for s in t["segments"]] == [(0, "大家好，今天開會", 4.0)]  # ids are kept (summary links use them)
    assert rec.transcript["segments"][0]["text"] == "大家好，今天開會"
    assert json.loads((rec.dir / "transcript.json").read_text(encoding="utf-8"))["edited"] is True
    assert c.get("/api/transcript", params={"session_id": sid, "media_id": "m1"}).json()["segments"][0]["text"] == "大家好，今天開會"
    r = c.put("/api/transcript", json={"session_id": sid, "media_id": "m1", "segments": [merged, {**SEGMENTS[2], "text": "謝謝大家"}]})
    assert [(s["id"], s["text"]) for s in r.json()["segments"]] == [(0, "大家好，今天開會"), (2, "謝謝大家")]


@pytest.mark.parametrize(
    "segments",
    [
        [{"id": 0, "start": 3.0, "end": 2.0, "text": "x"}],  # end before start
        [{"id": 0, "start": 0.0, "end": 60.0, "text": "x"}],  # beyond the media
        [{"id": 0, "start": 2.0, "end": 3.0, "text": "a"}, {"id": 1, "start": 1.0, "end": 2.0, "text": "b"}],  # out of order
        [{"id": 1, "start": 0.0, "end": 1.0, "text": "a"}, {"id": 1, "start": 1.0, "end": 2.0, "text": "b"}],  # duplicate id
    ],
)
def test_rejects_invalid_times(client, tmp_path, segments):
    c, sid, session = client
    _media(session, tmp_path)
    r = c.put("/api/transcript", json={"session_id": sid, "media_id": "m1", "segments": segments})
    assert r.status_code == 422


def test_cannot_edit_without_a_transcript(client, tmp_path):
    c, sid, session = client
    _media(session, tmp_path, transcript=False)
    r = c.put("/api/transcript", json={"session_id": sid, "media_id": "m1", "segments": []})
    assert r.status_code == 404


def test_player_streams_the_media_with_range_requests(client, tmp_path):
    c, sid, session = client
    rec = _media(session, tmp_path)
    q = {"session_id": sid, "media_id": "m1"}
    r = c.get("/api/media/file", params=q)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) == 10_240
    r = c.get("/api/media/file", params=q, headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and r.content == rec.path.read_bytes()[100:200]
    assert c.get("/api/media/file", params={**q, "kind": "audio"}).status_code == 404  # not extracted yet
    (rec.dir / "audio" / "audio.wav").write_bytes(b"RIFF")
    assert c.get("/api/media/file", params={**q, "kind": "audio"}).content == b"RIFF"
    assert c.get("/api/media/file", params={**q, "media_id": "other"}).status_code == 404


def test_player_accepts_the_token_in_the_url_only_on_that_path(tmp_path):
    app = create_app(Settings(auth_token="secret", data_dir=tmp_path / "data"))
    with TestClient(app) as c:
        auth = {"Authorization": "Bearer secret"}
        sid = c.post("/api/session", headers=auth).json()["session_id"]
        _media(app.state.sessions.get(sid), tmp_path)
        q = {"session_id": sid, "media_id": "m1"}
        assert c.get("/api/media/file", params=q).status_code == 401
        assert c.get("/api/media/file", params={**q, "token": "wrong"}).status_code == 401
        assert c.get("/api/media/file", params={**q, "token": "secret"}).status_code == 200
        # other paths still need the header
        assert c.get("/api/transcript", params={**q, "token": "secret"}).status_code == 401


def test_settings_round_trip(client):
    c, _, _ = client
    assert c.get("/api/settings").json() == {"device": "auto", "memory": "standard"}
    assert c.put("/api/settings", json={"device": "cpu", "memory": "low"}).json() == {"device": "cpu", "memory": "low"}
    assert c.get("/api/settings").json() == {"device": "cpu", "memory": "low"}
    assert c.put("/api/settings", json={"device": "gpu"}).status_code == 422
    info = c.get("/api/system/info").json()
    assert info["llm"]["device"] == "cpu" and info["llm"]["ctx"] == 4096


def test_storage_and_cleanup_keep_the_current_session(client, tmp_path):
    c, sid, session = client
    _media(session, tmp_path)
    stale = session.dir.parent / "old-session"
    (stale / "media").mkdir(parents=True)
    (stale / "media" / "x.bin").write_bytes(b"0" * 1000)
    cache = c.app.state.ytdlp.dir / "cache"
    cache.mkdir(parents=True)
    (cache / "player.js").write_bytes(b"0" * 500)
    s = c.get("/api/settings/storage").json()
    assert s["current_session_bytes"] >= 10_240 and s["stale_bytes"] == 1000 and s["cache_bytes"] == 500
    assert c.post("/api/settings/cleanup").json()["freed_bytes"] == 1500
    assert not stale.exists() and not cache.exists() and session.media.path.is_file()
