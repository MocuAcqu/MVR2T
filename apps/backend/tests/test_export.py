"""Phase 08: export of segments, transcript and summary (TXT / CSV / DOCX / print HTML / SRT / VTT / JSON / MD / ZIP)."""
from __future__ import annotations

import base64
import csv
import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document

from app.services.export import FORMATS, ExportError, ExportSource, build_export, clock, decode_png



def _png(w: int = 4, h: int = 2) -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\xff\xff\xff" * w for _ in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


PNG = _png()

SUMMARY = {
    "types": ["overview", "key_points", "action_items", "keywords", "qa", "notes", "topics", "mindmap"],
    "model": "Qwen3.5-4B",
    "results": {
        "overview": "中山店九月開幕，咖啡機延後。",
        "key_points": [{"text": "開幕日期可能延後", "refs": [1], "time": {"start": 65.2, "end": 70}}],
        "notes": [{"title": "人力", "bullets": ["缺兩位兼職", "師大合作"], "refs": [], "time": None}],
        "topics": [{"title": "會員", "description": "LINE 集點", "refs": [], "time": None}],
        "keywords": ["中山店", "LINE"],
        "action_items": [{"task": "寄出徵才資訊", "owner": "阿傑", "due": "週五", "refs": [2], "time": {"start": 3725, "end": 3730}}],
        "qa": [{"question": "POS 要換嗎？", "conclusion": "尚未定論", "refs": [], "time": None}],
        "mindmap": {
            "id": "n", "text": "AI 原始心智圖", "kind": "central", "refs": [], "time": None,
            "children": [{"id": "n-1", "text": "開幕", "kind": "main", "refs": [1], "time": {"start": 65.2, "end": 70}, "children": []}],
        },
    },
}
EDITED = {
    "id": "n", "text": "編輯後的中心", "kind": "central", "refs": [], "time": None,
    "children": [{"id": "n-1", "text": "開幕", "kind": "main", "refs": [], "time": None, "children": [
        {"id": "n-1-1", "text": "九月十號確認", "kind": "conclusion", "refs": [], "time": None, "children": []}]}],
}


@pytest.fixture()
def src(tmp_path: Path) -> ExportSource:
    seg_dir = tmp_path / "audio" / "segments"
    seg_dir.mkdir(parents=True)
    for i in range(2):
        (seg_dir / f"seg_{i:04d}.wav").write_bytes(b"RIFF" + bytes([i]) * 40)
    return ExportSource(
        filename="會議, \"一\".m4a",
        duration=125.5,
        audio={"segments": [
            {"index": 0, "start": 0.0, "end": 60.25, "duration": 60.25, "boundary": "silence"},
            {"index": 1, "start": 59.0, "end": 125.5, "duration": 66.5, "boundary": "end"},
        ]},
        audio_dir=tmp_path / "audio",
        transcript={"language": "Chinese", "timing": "aligned", "segments": [
            {"id": 0, "start": 0.5, "end": 3.25, "text": "大家好，今天開會。", "timing": "aligned", "words": []},
            {"id": 1, "start": 65.2, "end": 70.0, "text": "咖啡機延後兩週, \"可能\"影響開幕", "timing": "aligned", "words": []},
            {"id": 2, "start": 3725.0, "end": 3730.004, "text": "  ", "timing": "aligned", "words": []},
        ]},
        summary=SUMMARY,
    )


def read_csv(data: bytes) -> list[list[str]]:
    assert data.startswith(b"\xef\xbb\xbf"), "Excel needs a UTF-8 BOM"
    assert b"\r\n" in data
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def docx_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        parts += [c.text for row in t.rows for c in row.cells]
    return "\n".join(parts)


def test_every_supported_combination_builds(src: ExportSource) -> None:
    for content, formats in FORMATS.items():
        for fmt in formats:
            data, media_type = build_export(src, content, fmt)
            assert data and media_type


def test_unsupported_combinations_and_missing_data_are_clear_errors(src: ExportSource) -> None:
    with pytest.raises(ExportError) as e:
        build_export(src, "segments", "srt")
    assert e.value.status == 422
    for content, attr, words in (("transcript", "transcript", "語音辨識"), ("summary", "summary", "產生摘要"), ("segments", "audio", "抽取音訊")):
        empty = ExportSource(**{**src.__dict__, attr: None})
        with pytest.raises(ExportError) as e:
            build_export(empty, content, "txt" if content != "summary" else "md")
        assert e.value.status == 404 and words in e.value.message


def test_time_formats() -> None:
    assert clock(3725.004) == "01:02:05.004"
    assert clock(65.2, ",") == "00:01:05,200"
    assert clock(65.7, ms=False) == "00:01:05"


def test_transcript_subtitles_text_csv_json(src: ExportSource) -> None:
    srt = build_export(src, "transcript", "srt")[0].decode()
    assert srt.startswith("1\r\n00:00:00,500 --> 00:00:03,250\r\n大家好，今天開會。\r\n\r\n2\r\n00:01:05,200")
    assert "3725" not in srt and srt.count("-->") == 2  # empty sentence skipped
    vtt = build_export(src, "transcript", "vtt")[0].decode()
    assert vtt.startswith("WEBVTT\n\n00:00:00.500 --> 00:00:03.250\n")
    txt = build_export(src, "transcript", "txt")[0].decode()
    assert "[00:01:05] 咖啡機延後兩週" in txt and "共 2 句" in txt and "語言：中文" in txt
    rows = read_csv(build_export(src, "transcript", "csv")[0])
    assert rows[0] == ["編號", "開始（秒）", "結束（秒）", "開始", "結束", "文字"]
    assert rows[2] == ["1", "65.2", "70.0", "00:01:05.200", "00:01:10.000", "咖啡機延後兩週, \"可能\"影響開幕"]  # commas and quotes survive
    data = json.loads(build_export(src, "transcript", "json")[0])
    assert data["language"] == "Chinese" and len(data["segments"]) == 2


def test_transcript_docx_and_print_html(src: ExportSource) -> None:
    text = docx_text(build_export(src, "transcript", "docx")[0])
    assert "逐字稿：會議" in text and "00:01:05　咖啡機延後兩週" in text
    doc = Document(io.BytesIO(build_export(src, "transcript", "docx")[0]))
    rfonts = doc.styles["Normal"].element.rPr.rFonts
    assert rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia") == "Microsoft JhengHei"
    page = build_export(src, "transcript", "html")[0].decode()
    assert page.startswith("<!DOCTYPE html>") and "@page" in page and "Microsoft JhengHei" in page
    assert "&quot;可能&quot;" in page  # escaped


def test_segments_list_and_audio_zip(src: ExportSource) -> None:
    rows = read_csv(build_export(src, "segments", "csv")[0])
    assert rows[1] == ["1", "0.0", "60.25", "60.25", "00:00:00.000", "00:01:00.250", "停頓處"]
    assert "第 2 段　00:00:59.000 → 00:02:05.500　66.5 秒　結尾" in build_export(src, "segments", "txt")[0].decode()
    assert "硬切" not in docx_text(build_export(src, "segments", "docx")[0]) and "停頓處" in docx_text(build_export(src, "segments", "docx")[0])
    zf = zipfile.ZipFile(io.BytesIO(build_export(src, "segments_audio", "zip")[0]))
    assert zf.namelist() == ["seg_0000.wav", "seg_0001.wav", "segments.csv"]
    assert zf.read("seg_0001.wav") == b"RIFF" + bytes([1]) * 40
    (src.audio_dir / "segments" / "seg_0001.wav").unlink()  # type: ignore[operator]
    with pytest.raises(ExportError):
        build_export(src, "segments_audio", "zip")


def test_summary_uses_the_edited_mindmap_and_its_image(src: ExportSource) -> None:
    md = build_export(src, "summary", "md")[0].decode()
    assert md.index("## 全文摘要") < md.index("## 重點整理") < md.index("## 條列式筆記") < md.index("## 心智圖")
    assert "開幕日期可能延後（1:05）" in md and "負責：阿傑　期限：週五" in md and "AI 原始心智圖" in md
    edited = ExportSource(**{**src.__dict__, "mindmap": EDITED, "mindmap_png": PNG})
    md = build_export(edited, "summary", "md")[0].decode()
    assert "**編輯後的中心**" in md and "- 開幕" in md and "  - 【結論】九月十號確認" in md and "AI 原始心智圖" not in md
    rows = read_csv(build_export(edited, "summary", "csv")[0])
    assert ["行動事項", "寄出徵才資訊", "", "阿傑", "週五", "3725", "01:02:05"] in rows
    assert ["心智圖", "開幕 ／ 九月十號確認", "結論", "", "", "", ""] in rows
    data = json.loads(build_export(edited, "summary", "json")[0])
    assert data["results"]["mindmap"]["text"] == "編輯後的中心" and data["types"][-1] == "mindmap"
    doc = Document(io.BytesIO(build_export(edited, "summary", "docx")[0]))
    assert len(doc.inline_shapes) == 1  # the mind map picture
    assert "寄出徵才資訊" in docx_text(build_export(edited, "summary", "docx")[0])
    page = build_export(edited, "summary", "html")[0].decode()
    assert "data:image/png;base64," in page and "尚未定論" in page


def test_mindmap_png_is_validated() -> None:
    assert decode_png(base64.b64encode(PNG).decode()) == PNG
    for bad in ("not base64!", base64.b64encode(b"GIF89a").decode()):
        with pytest.raises(ExportError):
            decode_png(bad)


def test_a_broken_mindmap_picture_falls_back_to_an_outline(src: ExportSource) -> None:
    broken = ExportSource(**{**src.__dict__, "mindmap": EDITED, "mindmap_png": b"\x89PNG\r\n\x1a\n" + bytes(10)})
    text = docx_text(build_export(broken, "summary", "docx")[0])
    assert "【結論】九月十號確認" in text
