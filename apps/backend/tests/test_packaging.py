"""Phase 11 packaging helpers: FFmpeg LGPL build selection/extraction, bundled FFmpeg lookup, self-test."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path


from scripts import ffmpeg_bundle as fb


def test_picks_the_static_lgpl_7_1_build_from_a_dated_release():
    releases = [
        {"tag_name": "latest", "assets": [{"name": "ffmpeg-n7.1-latest-win64-lgpl-7.1.zip"}]},
        {"tag_name": "autobuild-2026-11-01-12-50", "assets": [
            {"name": "ffmpeg-n7.1.2-17-g3a5bc8f5a0-win64-gpl-7.1.zip"},
            {"name": "ffmpeg-n7.1.2-17-g3a5bc8f5a0-win64-lgpl-shared-7.1.zip"},
            {"name": "ffmpeg-n7.1.2-17-g3a5bc8f5a0-win64-lgpl-7.1.zip", "size": 1},
            {"name": "ffmpeg-n8.0-1-gabc-win64-lgpl-8.0.zip"},
        ]},
    ]
    rel, asset = fb.pick_asset(releases)
    assert rel["tag_name"].startswith("autobuild-") and asset["name"] == "ffmpeg-n7.1.2-17-g3a5bc8f5a0-win64-lgpl-7.1.zip"
    assert fb.pick_asset([releases[0]]) is None


def test_prepare_downloads_verifies_and_extracts(tmp_path, monkeypatch):
    from tests.test_model_manager import Server

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ffmpeg-n7.1.2-win64-lgpl-7.1/bin/ffmpeg.exe", b"ff")
        z.writestr("ffmpeg-n7.1.2-win64-lgpl-7.1/bin/ffprobe.exe", b"fp")
        z.writestr("ffmpeg-n7.1.2-win64-lgpl-7.1/bin/ffplay.exe", b"not needed")
        z.writestr("ffmpeg-n7.1.2-win64-lgpl-7.1/LICENSE.txt", b"GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n")
    data = buf.getvalue()
    server = Server()
    try:
        server.files["/f.zip"] = data
        pin = tmp_path / "ffmpeg.json"
        pin.write_text(json.dumps({
            "release": "autobuild-x", "filename": "f.zip", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "url": server.url + "/f.zip", "version": "n7.1.2", "license": "LGPL-3.0-or-later", "source": "https://github.com/FFmpeg/FFmpeg",
        }), encoding="utf-8")
        monkeypatch.setattr(fb, "PIN", pin)
        monkeypatch.setattr(fb, "OUT", tmp_path / "out")
        monkeypatch.setattr(fb, "CACHE", tmp_path / "cache")
        assert fb.prepare() == 0
        assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["LICENSE.txt", "SOURCE.txt", "ffmpeg.exe", "ffprobe.exe"]
        assert "LGPL" in (tmp_path / "out" / "SOURCE.txt").read_text(encoding="utf-8")
        # a tampered download is rejected
        pin.write_text(pin.read_text(encoding="utf-8").replace(hashlib.sha256(data).hexdigest(), "0" * 64), encoding="utf-8")
        assert fb.prepare() == 1
    finally:
        server.httpd.shutdown()


def test_bundled_ffmpeg_is_found_before_path_and_defaults_next_to_the_frozen_backend(tmp_path, monkeypatch):
    from app.core import config
    from app.engines.media import ffmpeg as ff

    bundled = tmp_path / "resources" / "ffmpeg"
    bundled.mkdir(parents=True)
    exe = ".exe" if sys.platform == "win32" else ""
    for n in ("ffmpeg", "ffprobe"):
        p = bundled / f"{n}{exe}"
        p.write_bytes(b"#!/bin/sh\n")
        p.chmod(0o755)
    loc = ff.locate_ffmpeg("", tmp_path / "none", str(bundled))
    assert loc is not None and loc.source == "bundled" and loc.ffmpeg.parent == bundled

    backend_exe = tmp_path / "resources" / "backend" / f"mvr2t-backend{exe}"
    backend_exe.parent.mkdir()
    backend_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(backend_exe))
    assert Path(config._bundled_ffmpeg_default()) == bundled.resolve()
    monkeypatch.setattr(sys, "frozen", False)
    assert config._bundled_ffmpeg_default() == ""


def test_self_test_reports_every_check(capsys, tmp_path):
    from app.selftest import run_self_test

    rc = run_self_test(["--models", str(tmp_path / "no-models")])
    out = json.loads(capsys.readouterr().out)
    for key in ("fastapi_app", "opencc_s2twp", "docx_export", "torch_cpu", "transformers_classes", "asr_processor", "hardware"):
        assert out[key]["ok"], (key, out[key])
    assert out["asr_processor"]["detail"].startswith("skipped")
    assert rc == (0 if out["ffmpeg"]["ok"] else 1)


def test_only_an_lgpl_license_is_accepted():
    assert fb.check_license("                   GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007") is None
    assert fb.check_license("                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007") is not None
    assert fb.LICENSE_ID == "LGPL-3.0-or-later"


def test_self_test_can_require_the_bundled_ffmpeg(capsys, tmp_path, monkeypatch):
    from app.selftest import run_self_test

    monkeypatch.setenv("MVR2T_BUNDLED_FFMPEG_DIR", str(tmp_path / "missing"))
    rc = run_self_test(["--models", str(tmp_path / "no-models"), "--expect-ffmpeg", "bundled"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and not out["ffmpeg"]["ok"]
