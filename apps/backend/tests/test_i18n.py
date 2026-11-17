"""英文介面：後端給畫面看的訊息都要有英文（app/core/i18n.py），回應翻譯只動訊息欄位。"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import i18n
from app.core.config import Settings
from app.main import create_app

APP = Path(__file__).resolve().parents[1] / "app"
#: 不是畫面上的訊息：模型提示詞、匯出文件的內容、自我檢查、內部除錯
SKIP = {"engines/llm/summarize.py", "services/export.py", "selftest.py", "core/i18n.py"}
CJK = re.compile(r"[一-鿿]")


def _skeleton(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)  # type: ignore[union-attr]
    return None


def ui_strings() -> set[str]:
    found: set[str] = set()
    for p in APP.rglob("*.py"):
        if p.relative_to(APP).as_posix() in SKIP:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        skip_ids = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
                first = n.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    skip_ids.add(id(first.value))
            if isinstance(n, ast.JoinedStr):
                skip_ids.update(id(v) for v in n.values)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
                skip_ids.add(id(n.value))
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "print":
                skip_ids.update(id(a) for a in n.args)  # console output for developers
        for n in ast.walk(tree):
            s = _skeleton(n)
            if s and id(n) not in skip_ids and CJK.search(s):
                found.add(s)
    return found


def test_every_backend_message_has_an_english_translation():
    missing = sorted(s for s in ui_strings() if s not in i18n.EN)
    assert not missing, "add these to app/core/i18n.py EN:\n" + "\n".join(missing)


def test_templates_and_sentences_are_translated():
    assert i18n.translate("第 3 / 12 段") == "Segment 3 / 12"
    assert i18n.translate("12 句") == "12 sentences"
    assert i18n.translate("摘要與心智圖已在處理中。") == "Summary and mind map is already being processed."
    two = "尚未安裝 llama.cpp（摘要用的執行程式）。請到「模型管理」下載「摘要與心智圖」。"
    assert i18n.translate(two) == "llama.cpp (the program that runs the summary) is not installed. Download “Summary and mind map” in Models."
    assert i18n.translate("大家好今天開會") == "大家好今天開會"  # user content is never in the table
    assert i18n.translate("語音辨識", "zh-TW") == "語音辨識"


def test_only_message_fields_are_translated():
    data = {"stage": "正在辨識語音", "detail": "第 1 / 2 段", "result": {"text": "語音辨識", "warnings": ["尚未下載時間戳記對齊模型，時間為依字數估計。"]}}
    out = i18n.translate_json(data, "en")
    assert out["stage"] == "Recognizing speech" and out["detail"] == "Segment 1 / 2"
    assert out["result"]["text"] == "語音辨識"  # content field untouched
    assert out["result"]["warnings"][0].startswith("The timestamp alignment model")


def test_api_answers_in_english_when_asked(tmp_path):
    app = create_app(Settings(auth_token="", data_dir=tmp_path / "data"))
    with TestClient(app) as c:
        en = {"X-MVR2T-Lang": "en"}
        r = c.get("/api/transcript", params={"session_id": "nope", "media_id": "x"}, headers=en)
        assert r.status_code == 404 and r.json()["detail"] == "The session has ended. Please import the file again."
        assert c.get("/api/transcript", params={"session_id": "nope", "media_id": "x"}).json()["detail"].startswith("工作階段")
        models = c.get("/api/models", headers=en).json()
        assert {p["name"] for p in models["packages"]} >= {"Speech recognition", "Summary and mind map"}
        assert c.get("/api/settings", headers=en).json() == {"device": "auto", "memory": "standard"}
        # transcript: warnings are translated, the sentences are not
        sid = c.post("/api/session").json()["session_id"]
        from tests.test_editor_settings import _media

        rec = _media(app.state.sessions.get(sid), tmp_path)
        rec.transcript["warnings"] = ["這份逐字稿來自影片作者提供的字幕（中文（简体）），沒有經過語音辨識。"]
        tr = c.get("/api/transcript", params={"session_id": sid, "media_id": "m1"}, headers=en).json()
        assert tr["warnings"][0].startswith("This transcript comes from the subtitles") and tr["segments"][0]["text"] == "大家好"
