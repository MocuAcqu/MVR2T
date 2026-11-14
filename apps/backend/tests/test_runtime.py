"""llama.cpp runtime archive handling (app/models/runtime.py): safe extraction of .zip and .tar.gz."""
from __future__ import annotations

import io
import sys
import tarfile
import zipfile

import pytest

from app.models.runtime import LLAMA_CPP, LlamaRuntimeError, asset_for, extract_archive


def test_pinned_release_has_a_windows_cpu_build():
    a = asset_for(LLAMA_CPP, "win-cpu-x64")
    assert LLAMA_CPP.tag and a is not None and len(a.sha256) == 64 and a.filename.endswith(".zip")


def test_zip_extracts_and_rejects_paths_outside(tmp_path):
    ok = tmp_path / "ok.zip"
    with zipfile.ZipFile(ok, "w") as z:
        z.writestr("build/bin/llama-server.exe", b"exe")
    extract_archive(ok, "ok.zip", tmp_path / "out")
    assert (tmp_path / "out" / "build" / "bin" / "llama-server.exe").read_bytes() == b"exe"

    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.txt", b"x")
    with pytest.raises(LlamaRuntimeError, match="不安全"):
        extract_archive(bad, "bad.zip", tmp_path / "out2")
    assert not (tmp_path / "evil.txt").exists()


def _tar(path, entries):  # noqa: ANN001
    with tarfile.open(path, "w:gz") as tf:
        for name, kind, data in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            else:
                info.type = tarfile.SYMTYPE
                info.linkname = data
                tf.addfile(info)


@pytest.mark.skipif(sys.platform == "win32", reason=".tar.gz builds are for macOS; symlinks need extra rights on Windows")
def test_tar_gz_extracts_with_relative_links(tmp_path):
    ok = tmp_path / "ok.tar.gz"
    _tar(ok, [("build/bin/llama-server", "file", b"bin"), ("build/bin/libggml.0.dylib", "file", b"lib"),
              ("build/bin/libggml.dylib", "link", "libggml.0.dylib")])
    extract_archive(ok, "ok.tar.gz", tmp_path / "out")
    assert (tmp_path / "out" / "build" / "bin" / "llama-server").read_bytes() == b"bin"


@pytest.mark.parametrize("entries", [
    [("../evil", "file", b"x")],
    [("bin/escape", "link", "../../../etc/passwd")],
    [("bin/abs", "link", "/etc/passwd")],
])
def test_tar_gz_rejects_traversal_and_escaping_links(tmp_path, entries):
    bad = tmp_path / "bad.tar.gz"
    _tar(bad, entries)
    with pytest.raises(LlamaRuntimeError):
        extract_archive(bad, "bad.tar.gz", tmp_path / "out")


def test_resolve_script_prints_cpu_cuda_and_cudart_assets(monkeypatch, capsys):
    """Phase 10: the pinning script also lists the NVIDIA build (CUDA 12.x preferred) and its cudart libraries."""
    from scripts import resolve_llama_release as r

    names = ["llama-b9-bin-win-cpu-x64.zip", "llama-b9-bin-win-cuda-12.4-x64.zip", "llama-b9-bin-win-cuda-13.1-x64.zip",
             "cudart-llama-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-13.1-x64.zip", "llama-b9-bin-macos-arm64.tar.gz"]
    rel = {"assets": [{"name": n, "size": i + 1, "digest": f"sha256:{i:064d}", "browser_download_url": ""} for i, n in enumerate(names)]}

    def fake_get(url):  # noqa: ANN001, ANN202
        return rel if "/releases/" in url else {"sha": "abc123"}

    monkeypatch.setattr(r, "_get", fake_get)
    assert r.main(["--tag", "b9"]) == 0
    out = capsys.readouterr().out
    assert 'RuntimeAsset("win-cpu-x64", "llama-b9-bin-win-cpu-x64.zip"' in out
    assert 'RuntimeAsset("win-cuda-12.4-x64", "llama-b9-bin-win-cuda-12.4-x64.zip"' in out
    assert 'RuntimeAsset("win-cuda-12.4-x64:cudart", "cudart-llama-bin-win-cuda-12.4-x64.zip"' in out
    assert "13.1-x64.zip" not in out and 'RuntimeAsset("macos-arm64"' in out
