"""匯出（PROJECT_SPEC §G、Phase 08）：把本次 Session 的切段、逐字稿、摘要轉成檔案內容。

- 全部在記憶體中產生，回傳 bytes；寫到哪裡由使用者在 Electron 的對話框選擇（後端不寫入任何 Session 以外的地方）。
- CSV 一律 UTF-8 含 BOM、CRLF：Excel 直接開啟才不會亂碼。
- DOCX 用 python-docx；中文字型指定為 eastAsia「Microsoft JhengHei」（Windows 內建；其他系統由 Word 替代）。
- PDF 由 Electron 把這裡產生的列印用 HTML（format = html）以 Chromium 轉成 PDF，字型自動嵌入。
- 摘要的心智圖使用前端「編輯後」的版本（請求中的 mindmap / mindmap_png）；沒有就用 AI 產生的原始版本。
"""
from __future__ import annotations

import base64
import binascii
import csv
import html
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

ExportContent = Literal["segments", "segments_audio", "transcript", "summary"]
ExportFormat = Literal["txt", "csv", "docx", "html", "srt", "vtt", "json", "md", "zip"]

FORMATS: dict[str, tuple[str, ...]] = {
    "segments": ("txt", "csv", "docx", "html"),
    "segments_audio": ("zip",),
    "transcript": ("txt", "srt", "vtt", "json", "csv", "docx", "html"),
    "summary": ("md", "txt", "csv", "json", "docx", "html"),
}

MEDIA_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "zip": "application/zip",
}

BOUNDARY_LABELS = {"silence": "停頓處", "hard": "硬切（重疊）", "end": "結尾"}
SUMMARY_LABELS = {
    "overview": "全文摘要",
    "key_points": "重點整理",
    "notes": "條列式筆記",
    "topics": "主題分類",
    "keywords": "關鍵字",
    "action_items": "行動事項",
    "qa": "問題與結論",
    "mindmap": "心智圖",
}
SUMMARY_ORDER = ("overview", "key_points", "notes", "topics", "keywords", "action_items", "qa")
MAX_MINDMAP_PNG = 20 * 1024 * 1024
CJK_FONT = "Microsoft JhengHei"
PRINT_FONTS = "'Microsoft JhengHei', 'PingFang TC', 'Noto Sans CJK TC', 'Noto Sans TC', sans-serif"


class ExportError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class ExportSource:
    """匯出需要的資料（由 Session 的 MediaRecord 取出）。"""

    filename: str
    duration: float
    audio: dict[str, Any] | None
    audio_dir: Path | None
    transcript: dict[str, Any] | None
    summary: dict[str, Any] | None
    mindmap: dict[str, Any] | None = None  # 前端編輯後的心智圖
    mindmap_png: bytes | None = None
    summary_types: list[str] | None = None  # 只匯出這些摘要類型（含 "mindmap"）；None = 全部


# ---------------------------------------------------------------------------
# 時間格式
# ---------------------------------------------------------------------------


def clock(seconds: float, sep: str = ".", ms: bool = True) -> str:
    """hh:mm:ss.mmm（SRT 用逗號）。"""
    total_ms = max(0, round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    base = f"{h:02d}:{m:02d}:{s:02d}"
    return f"{base}{sep}{milli:03d}" if ms else base


def short_clock(seconds: float) -> str:
    """畫面上顯示的時間：m:ss 或 h:mm:ss。"""
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def decode_png(data: str | None) -> bytes | None:
    if not data:
        return None
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ExportError(422, "心智圖圖片格式不正確。") from None
    if len(raw) > MAX_MINDMAP_PNG or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ExportError(422, "心智圖圖片格式不正確。")
    return raw


# ---------------------------------------------------------------------------
# 共用：CSV、DOCX、HTML
# ---------------------------------------------------------------------------


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _text(lines: list[str]) -> bytes:
    return ("\r\n".join(lines).rstrip() + "\r\n").encode("utf-8")


THEME_FONT_ATTRS = ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme")


def _force_fonts(rpr: Any) -> None:
    """把 rPr 的字型固定為微軟正黑體，並移除主題字型屬性。
    Word 中主題字型（w:eastAsiaTheme 等）的優先權高於明確的字型名稱；python-docx 範本的標題樣式帶有
    majorEastAsia，而範本主題的東亞字型是空的，Word 會改用日文的 MS Gothic（2026-11-11 Windows 驗收發現）。"""
    from docx.oxml.ns import qn

    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.insert(0, fonts)
    for attr in THEME_FONT_ATTRS:
        fonts.attrib.pop(qn(f"w:{attr}"), None)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attr}"), CJK_FONT)
    lang = rpr.find(qn("w:lang"))
    if lang is not None:
        lang.set(qn("w:eastAsia"), "zh-TW")


def _new_doc(title: str, meta: str) -> Any:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    doc = Document()
    styles_el = doc.styles.element
    # 文件預設值（docDefaults）＋所有樣式：都改成微軟正黑體、東亞語言 zh-TW
    defaults = styles_el.find(qn("w:docDefaults"))
    if defaults is not None:
        rpr_default = defaults.find(qn("w:rPrDefault"))
        if rpr_default is not None:
            rpr = rpr_default.find(qn("w:rPr"))
            if rpr is None:
                rpr = rpr_default.makeelement(qn("w:rPr"), {})
                rpr_default.append(rpr)
            _force_fonts(rpr)
    # 所有樣式（含表格樣式的條件格式）裡的 rFonts
    for rpr in [f.getparent() for f in styles_el.iter(qn("w:rFonts"))]:
        _force_fonts(rpr)
    for name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3", "List Bullet", "List Number"):
        try:
            style = doc.styles[name]
        except KeyError:
            continue
        _force_fonts(style.element.get_or_add_rPr())
        if name != "Normal":
            style.font.color.rgb = RGBColor(0, 0, 0)
    doc.styles["Normal"].font.size = Pt(11)
    doc.core_properties.title = title
    doc.add_heading(title, level=0)
    p = doc.add_paragraph(meta)
    p.runs[0].font.color.rgb = RGBColor(0x4B, 0x4B, 0x4B)
    p.runs[0].font.size = Pt(9)
    return doc


def _doc_bytes(doc: Any) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _gray_run(paragraph: Any, text: str) -> None:
    from docx.shared import Pt, RGBColor

    r = paragraph.add_run(text)
    r.font.color.rgb = RGBColor(0x4B, 0x4B, 0x4B)
    r.font.size = Pt(9)


def _table(doc: Any, header: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for cell, text in zip(t.rows[0].cells, header):
        cell.text = text
        cell.paragraphs[0].runs[0].font.bold = True
    for row in rows:
        cells = t.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = text


def _html(title: str, meta: str, body: str) -> bytes:
    e = html.escape
    page = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>{e(title)}</title>
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: {PRINT_FONTS}; color: #000; font-size: 10.5pt; line-height: 1.6; margin: 0; }}
h1 {{ font-size: 18pt; margin: 0 0 4pt; }}
h2 {{ font-size: 13pt; margin: 16pt 0 6pt; border-bottom: 1.5pt solid #000; padding-bottom: 2pt; break-after: avoid; }}
h3 {{ font-size: 11pt; margin: 10pt 0 4pt; break-after: avoid; }}
.meta {{ color: #4b4b4b; font-size: 9pt; margin-bottom: 12pt; }}
.t {{ color: #4b4b4b; font-size: 8.5pt; font-variant-numeric: tabular-nums; white-space: nowrap; }}
table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; }}
th, td {{ border: 0.75pt solid #afafaf; padding: 3pt 6pt; text-align: left; vertical-align: top; }}
th {{ background: #efefef; }}
tr {{ break-inside: avoid; }}
.line {{ display: flex; gap: 10pt; break-inside: avoid; margin: 0 0 3pt; }}
.line .t {{ width: 58pt; flex: none; padding-top: 1pt; }}
ul, ol {{ margin: 0 0 6pt; padding-left: 18pt; }}
li {{ margin: 2pt 0; }}
.chip {{ display: inline-block; background: #efefef; border-radius: 99pt; padding: 0 6pt; margin: 0 4pt 4pt 0; }}
.mm {{ width: 100%; margin-top: 6pt; }}
.sub {{ color: #4b4b4b; }}
</style></head>
<body><h1>{e(title)}</h1><div class="meta">{e(meta)}</div>
{body}
</body></html>"""
    return page.encode("utf-8")


def _meta(src: ExportSource, extra: str = "") -> str:
    parts = [f"原始檔案：{src.filename}", f"長度：{short_clock(src.duration)}", f"匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if extra:
        parts.append(extra)
    return "　".join(parts)


# ---------------------------------------------------------------------------
# 切段
# ---------------------------------------------------------------------------


def _segments(src: ExportSource) -> list[dict[str, Any]]:
    if not src.audio or not src.audio.get("segments"):
        raise ExportError(404, "還沒有抽取音訊與切段，請先完成「抽取音訊」。")
    return list(src.audio["segments"])


def export_segments(src: ExportSource, fmt: str) -> bytes:
    segs = _segments(src)
    title = f"切段清單：{src.filename}"
    meta = _meta(src, f"共 {len(segs)} 段")
    rows = [
        [str(s["index"] + 1), clock(s["start"]), clock(s["end"]), f"{s['duration']:.1f}", BOUNDARY_LABELS.get(s["boundary"], s["boundary"])]
        for s in segs
    ]
    header = ["段", "開始", "結束", "長度（秒）", "切點"]
    if fmt == "txt":
        lines = [title, meta, ""]
        lines += [f"第 {r[0]} 段　{r[1]} → {r[2]}　{r[3]} 秒　{r[4]}" for r in rows]
        return _text(lines)
    if fmt == "csv":
        return _csv(
            ["段", "開始（秒）", "結束（秒）", "長度（秒）", "開始", "結束", "切點"],
            [[s["index"] + 1, s["start"], s["end"], s["duration"], clock(s["start"]), clock(s["end"]), r[4]] for s, r in zip(segs, rows)],
        )
    if fmt == "docx":
        doc = _new_doc(title, meta)
        _table(doc, header, rows)
        return _doc_bytes(doc)
    if fmt == "html":
        e = html.escape
        body = "<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in header) + "</tr></thead><tbody>"
        body += "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>"
        return _html(title, meta, body)
    raise ExportError(422, f"切段清單不支援 {fmt}。")


def export_segments_audio(src: ExportSource) -> bytes:
    segs = _segments(src)
    if src.audio_dir is None:
        raise ExportError(404, "找不到切段音檔。")
    buf = io.BytesIO()
    # WAV 幾乎無法再壓縮：用 STORED，速度快
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        for s in segs:
            path = src.audio_dir / "segments" / f"seg_{s['index']:04d}.wav"
            if not path.is_file():
                raise ExportError(404, "找不到切段音檔，請重新抽取音訊。")
            zf.write(path, f"seg_{s['index']:04d}.wav")
        zf.writestr("segments.csv", export_segments(src, "csv"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 逐字稿
# ---------------------------------------------------------------------------

LANG_LABELS = {"Chinese": "中文", "English": "英文", "Cantonese": "粵語", "Japanese": "日文", "Korean": "韓文"}


def _transcript(src: ExportSource) -> dict[str, Any]:
    if not src.transcript or not src.transcript.get("segments"):
        raise ExportError(404, "還沒有逐字稿，請先完成「語音辨識」。")
    return src.transcript


def export_transcript(src: ExportSource, fmt: str) -> bytes:
    tr = _transcript(src)
    segs = [s for s in tr["segments"] if str(s.get("text", "")).strip()]
    title = f"逐字稿：{src.filename}"
    lang = tr.get("language")
    meta = _meta(src, f"語言：{LANG_LABELS.get(lang, lang or '未知')}　共 {len(segs)} 句")
    if fmt == "txt":
        return _text([title, meta, ""] + [f"[{clock(s['start'], ms=False)}] {s['text'].strip()}" for s in segs])
    if fmt == "srt":
        blocks = [f"{i}\r\n{clock(s['start'], ',')} --> {clock(s['end'], ',')}\r\n{s['text'].strip()}\r\n" for i, s in enumerate(segs, 1)]
        return "\r\n".join(blocks).encode("utf-8")
    if fmt == "vtt":
        blocks = [f"{clock(s['start'])} --> {clock(s['end'])}\n{s['text'].strip()}\n" for s in segs]
        return ("WEBVTT\n\n" + "\n".join(blocks)).encode("utf-8")
    if fmt == "json":
        data = {
            "file": src.filename,
            "duration": src.duration,
            "language": lang,
            "timing": tr.get("timing"),
            "segments": [
                {"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"].strip(), "timing": s.get("timing"), "words": s.get("words", [])}
                for s in segs
            ],
        }
        return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if fmt == "csv":
        return _csv(
            ["編號", "開始（秒）", "結束（秒）", "開始", "結束", "文字"],
            [[s["id"], s["start"], s["end"], clock(s["start"]), clock(s["end"]), s["text"].strip()] for s in segs],
        )
    if fmt == "docx":
        doc = _new_doc(title, meta)
        for s in segs:
            p = doc.add_paragraph()
            _gray_run(p, f"{clock(s['start'], ms=False)}　")
            p.add_run(s["text"].strip())
        return _doc_bytes(doc)
    if fmt == "html":
        e = html.escape
        body = "".join(f'<div class="line"><span class="t">{clock(s["start"], ms=False)}</span><span>{e(s["text"].strip())}</span></div>' for s in segs)
        return _html(title, meta, body)
    raise ExportError(422, f"逐字稿不支援 {fmt}。")


# ---------------------------------------------------------------------------
# 摘要
# ---------------------------------------------------------------------------


def _summary(src: ExportSource) -> tuple[dict[str, Any], list[str], dict[str, Any] | None]:
    if not src.summary:
        raise ExportError(404, "還沒有摘要，請先「產生摘要」。")
    results = src.summary.get("results", {})
    wanted = set(src.summary_types) if src.summary_types is not None else None
    types = [
        t for t in SUMMARY_ORDER
        if t in src.summary.get("types", []) and results.get(t) not in (None, [], "") and (wanted is None or t in wanted)
    ]
    mindmap = src.mindmap if src.mindmap is not None else results.get("mindmap")
    if wanted is not None and "mindmap" not in wanted:
        mindmap = None
    if not types and not mindmap:
        raise ExportError(404 if wanted is None else 422, "摘要沒有內容可以匯出。" if wanted is None else "請至少勾選一種摘要類型。")
    return results, types, mindmap


def _t(item: dict[str, Any]) -> str:
    time = item.get("time")
    return short_clock(time["start"]) if isinstance(time, dict) and "start" in time else ""


def _with_t(text: str, item: dict[str, Any]) -> str:
    t = _t(item)
    return f"{text}（{t}）" if t else text


def _mindmap_lines(node: dict[str, Any], depth: int = 0, md: bool = False) -> list[str]:
    """心智圖 → 縮排條列（Markdown 或純文字）。"""
    text = node.get("text", "")
    if node.get("kind") == "conclusion":
        text = f"【結論】{text}"
    text = _with_t(text, node)
    if depth == 0:
        lines = [f"**{text}**" if md else text]
    else:
        lines = [("  " * (depth - 1)) + ("- " if md else "・") + text]
    for c in node.get("children", []):
        lines += _mindmap_lines(c, depth + 1, md)
    return lines


def _summary_md_or_txt(src: ExportSource, md: bool) -> bytes:
    results, types, mindmap = _summary(src)
    h2 = (lambda s: f"## {s}") if md else (lambda s: f"【{s}】")
    bullet = "- " if md else "・"
    title = f"摘要：{src.filename}"
    lines = [f"# {title}" if md else title, "", _meta(src, f"模型：{src.summary.get('model', '')}"), ""]  # type: ignore[union-attr]
    for t in types:
        r = results[t]
        lines.append(h2(SUMMARY_LABELS[t]))
        lines.append("")
        if t == "overview":
            lines.append(str(r))
        elif t == "key_points":
            lines += [f"{i}. {_with_t(p['text'], p)}" for i, p in enumerate(r, 1)]
        elif t == "notes":
            for s in r:
                lines.append(f"### {_with_t(s['title'], s)}" if md else _with_t(s["title"], s))
                lines += [f"{bullet}{b}" for b in s.get("bullets", [])]
                lines.append("")
        elif t == "topics":
            lines += [f"{bullet}{'**' if md else ''}{_with_t(x['title'], x)}{'**' if md else ''}：{x.get('description', '')}" for x in r]
        elif t == "keywords":
            lines.append("、".join(r))
        elif t == "action_items":
            lines += [
                f"{bullet}{_with_t(a['task'], a)}　負責：{a.get('owner') or '未指定'}　期限：{a.get('due') or '未提到'}" for a in r
            ]
        elif t == "qa":
            for q in r:
                lines.append(f"{bullet}{'**' if md else ''}{_with_t(q['question'], q)}{'**' if md else ''}")
                lines.append(f"  {q.get('conclusion', '')}" if md else f"　{q.get('conclusion', '')}")
        lines.append("")
    if mindmap:
        lines.append(h2(SUMMARY_LABELS["mindmap"]))
        lines.append("")
        lines += _mindmap_lines(mindmap, md=md)
        lines.append("")
    return _text(lines)


def _summary_csv(src: ExportSource) -> bytes:
    results, types, mindmap = _summary(src)
    rows: list[list[Any]] = []

    def row(t: str, title: str, content: str = "", owner: str = "", due: str = "", item: dict[str, Any] | None = None) -> None:
        time = (item or {}).get("time")
        start = time["start"] if isinstance(time, dict) else ""
        rows.append([SUMMARY_LABELS[t], title, content, owner, due, start, clock(start, ms=False) if start != "" else ""])

    for t in types:
        r = results[t]
        if t == "overview":
            row(t, "", str(r))
        elif t == "key_points":
            for p in r:
                row(t, p["text"], item=p)
        elif t == "notes":
            for s in r:
                for b in s.get("bullets", []) or [""]:
                    row(t, s["title"], b, item=s)
        elif t == "topics":
            for x in r:
                row(t, x["title"], x.get("description", ""), item=x)
        elif t == "keywords":
            for k in r:
                row(t, k)
        elif t == "action_items":
            for a in r:
                row(t, a["task"], "", a.get("owner", ""), a.get("due", ""), item=a)
        elif t == "qa":
            for q in r:
                row(t, q["question"], q.get("conclusion", ""), item=q)
    if mindmap:

        def walk(n: dict[str, Any], path: list[str]) -> None:
            for c in n.get("children", []):
                row("mindmap", " ／ ".join([*path, c["text"]]), "結論" if c.get("kind") == "conclusion" else "", item=c)
                walk(c, [*path, c["text"]])

        walk(mindmap, [])
    return _csv(["類型", "項目", "內容", "負責人", "期限", "時間（秒）", "時間"], rows)


def _summary_json(src: ExportSource) -> bytes:
    results, types, mindmap = _summary(src)
    data = {
        "file": src.filename,
        "duration": src.duration,
        "model": src.summary.get("model"),  # type: ignore[union-attr]
        "types": types + (["mindmap"] if mindmap else []),
        "results": {**{t: results[t] for t in types}, **({"mindmap": mindmap} if mindmap else {})},
    }
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _summary_docx(src: ExportSource) -> bytes:
    results, types, mindmap = _summary(src)
    doc = _new_doc(f"摘要：{src.filename}", _meta(src, f"模型：{src.summary.get('model', '')}"))  # type: ignore[union-attr]

    def item(style: str, text: str, it: dict[str, Any]) -> Any:
        p = doc.add_paragraph(style=style)
        p.add_run(text)
        if _t(it):
            _gray_run(p, f"　{_t(it)}")
        return p

    for t in types:
        r = results[t]
        doc.add_heading(SUMMARY_LABELS[t], level=1)
        if t == "overview":
            doc.add_paragraph(str(r))
        elif t == "key_points":
            for p in r:
                item("List Number", p["text"], p)
        elif t == "notes":
            for s in r:
                h = doc.add_heading(s["title"], level=2)
                if _t(s):
                    _gray_run(h, f"　{_t(s)}")
                for b in s.get("bullets", []):
                    doc.add_paragraph(b, style="List Bullet")
        elif t == "topics":
            for x in r:
                p = item("List Bullet", x["title"], x)
                p.runs[0].font.bold = True
                p.add_run(f"：{x.get('description', '')}")
        elif t == "keywords":
            doc.add_paragraph("、".join(r))
        elif t == "action_items":
            _table(doc, ["事項", "負責", "期限", "時間"], [[a["task"], a.get("owner") or "未指定", a.get("due") or "未提到", _t(a)] for a in r])
        elif t == "qa":
            for q in r:
                p = item("List Bullet", q["question"], q)
                p.runs[0].font.bold = True
                doc.add_paragraph(q.get("conclusion", ""))
    if mindmap:
        doc.add_heading(SUMMARY_LABELS["mindmap"], level=1)
        added = False
        if src.mindmap_png:
            section = doc.sections[-1]
            width = section.page_width - section.left_margin - section.right_margin
            try:
                doc.add_picture(io.BytesIO(src.mindmap_png), width=width)
                added = True
            except Exception:  # noqa: BLE001 - 圖片讀不了就改用條列，不讓整份匯出失敗
                added = False
        if not added:
            for line in _mindmap_lines(mindmap):
                doc.add_paragraph(line)
    return _doc_bytes(doc)


def _summary_html(src: ExportSource) -> bytes:
    results, types, mindmap = _summary(src)
    e = html.escape

    def tchip(it: dict[str, Any]) -> str:
        return f' <span class="t">{_t(it)}</span>' if _t(it) else ""

    parts: list[str] = []
    for t in types:
        r = results[t]
        parts.append(f"<h2>{e(SUMMARY_LABELS[t])}</h2>")
        if t == "overview":
            parts.append(f"<p>{e(str(r))}</p>")
        elif t == "key_points":
            parts.append("<ol>" + "".join(f"<li>{e(p['text'])}{tchip(p)}</li>" for p in r) + "</ol>")
        elif t == "notes":
            for s in r:
                parts.append(f"<h3>{e(s['title'])}{tchip(s)}</h3><ul>" + "".join(f"<li>{e(b)}</li>" for b in s.get("bullets", [])) + "</ul>")
        elif t == "topics":
            parts.append("<ul>" + "".join(f"<li><b>{e(x['title'])}</b>{tchip(x)}：{e(x.get('description', ''))}</li>" for x in r) + "</ul>")
        elif t == "keywords":
            parts.append("<p>" + "".join(f'<span class="chip">{e(k)}</span>' for k in r) + "</p>")
        elif t == "action_items":
            parts.append(
                "<table><thead><tr><th>事項</th><th>負責</th><th>期限</th><th>時間</th></tr></thead><tbody>"
                + "".join(
                    f"<tr><td>{e(a['task'])}</td><td>{e(a.get('owner') or '未指定')}</td><td>{e(a.get('due') or '未提到')}</td>"
                    f'<td class="t">{_t(a)}</td></tr>'
                    for a in r
                )
                + "</tbody></table>"
            )
        elif t == "qa":
            parts.append(
                "<ul>" + "".join(f"<li><b>{e(q['question'])}</b>{tchip(q)}<br><span class=\"sub\">{e(q.get('conclusion', ''))}</span></li>" for q in r) + "</ul>"
            )
    if mindmap:
        parts.append(f'<h2 style="break-before: page">{e(SUMMARY_LABELS["mindmap"])}</h2>')
        if src.mindmap_png:
            b64 = base64.b64encode(src.mindmap_png).decode("ascii")
            parts.append(f'<img class="mm" alt="心智圖" src="data:image/png;base64,{b64}">')
        else:
            parts.append("<pre>" + e("\n".join(_mindmap_lines(mindmap))) + "</pre>")
    return _html(f"摘要：{src.filename}", _meta(src, f"模型：{src.summary.get('model', '')}"), "".join(parts))  # type: ignore[union-attr]


def export_summary(src: ExportSource, fmt: str) -> bytes:
    if fmt == "md":
        return _summary_md_or_txt(src, md=True)
    if fmt == "txt":
        return _summary_md_or_txt(src, md=False)
    if fmt == "csv":
        return _summary_csv(src)
    if fmt == "json":
        return _summary_json(src)
    if fmt == "docx":
        return _summary_docx(src)
    if fmt == "html":
        return _summary_html(src)
    raise ExportError(422, f"摘要不支援 {fmt}。")


def build_export(src: ExportSource, content: str, fmt: str) -> tuple[bytes, str]:
    """回傳 (檔案內容, Content-Type)。"""
    if fmt not in FORMATS.get(content, ()):
        raise ExportError(422, f"不支援的匯出組合：{content} / {fmt}")
    if content == "segments":
        data = export_segments(src, fmt)
    elif content == "segments_audio":
        data = export_segments_audio(src)
    elif content == "transcript":
        data = export_transcript(src, fmt)
    else:
        data = export_summary(src, fmt)
    return data, MEDIA_TYPES[fmt]
