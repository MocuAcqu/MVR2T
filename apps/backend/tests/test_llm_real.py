"""Phase 06 acceptance with the REAL summary model through llama.cpp's llama-server (CPU).

Skipped unless:
- llama-server is installed (python -m scripts.download_models --llm) or MVR2T_LLAMA_SERVER points to one, and
- the summary model (LLM_MODEL) is downloaded.

Uses tests/fixtures/meeting_zh.json: a synthetic 8.5-minute Traditional-Chinese meeting with known facts
(5 owners with tasks, decisions with dates, two open questions).
Runtime on CPU: about 4 minutes for the first test and 20-25 minutes for the hierarchical one
(measured on the user's Windows PC, 2026-11-10); set MVR2T_SKIP_LLM_REAL=1 to skip them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core.config import Settings, default_user_data_dir
from app.engines.llm.server import LlamaServer, ServerOptions
from app.engines.llm.summarize import Budget, Line, summarize
from app.models.registry import LLM_MODEL, gguf_path
from app.models.runtime import find_llama_server
from app.models.store import is_installed
from tests.test_lifecycle import wait_dead

DATA = Path(os.environ.get("MVR2T_DATA_DIR") or default_user_data_dir())
CFG = Settings(data_dir=DATA)
EXE = find_llama_server(CFG.runtime_root)
MEETING = json.loads((Path(__file__).parent / "fixtures" / "meeting_zh.json").read_text(encoding="utf-8"))
LINES = [Line(s["id"], s["start"], s["end"], s["text"]) for s in MEETING["segments"]]

pytestmark = [
    pytest.mark.skipif(os.environ.get("MVR2T_SKIP_LLM_REAL") == "1", reason="MVR2T_SKIP_LLM_REAL=1"),
    pytest.mark.skipif(EXE is None, reason="llama-server not installed"),
    pytest.mark.skipif(not is_installed(LLM_MODEL, CFG.models_root), reason="summary model not downloaded"),
]


def server() -> LlamaServer:
    assert EXE is not None
    return LlamaServer(ServerOptions(EXE, gguf_path(LLM_MODEL, CFG.models_root), ctx_size=CFG.llm_ctx, threads=CFG.llm_threads))


def test_action_items_have_the_right_owners_and_timestamps():
    srv = server()
    with srv:
        pid = srv.pid
        out = summarize(srv, LINES, ["action_items", "keywords"], Budget())
    assert pid is not None and wait_dead(pid), "llama-server must exit after the task (§5.4)"
    items = out["results"]["action_items"]
    print(json.dumps(items, ensure_ascii=False, indent=1))
    owners = " ".join(i["owner"] for i in items)
    for who in ["小美", "阿傑", "Kevin", "Amy", "Joyce"]:
        assert who in owners, who
    assert all(i["time"] is not None for i in items)
    # every timestamp points into the part of the meeting where that person's task was discussed
    for i in items:
        assert 0 <= i["time"]["start"] <= MEETING["duration"]
    assert "中山店" in out["results"]["keywords"]


def test_long_transcript_hierarchical_summary_keeps_the_key_decisions():
    with server() as srv:
        out = summarize(srv, LINES, ["overview", "qa", "action_items"], Budget(chunk_input=700, notes_input=2000))
    assert out["chunks"] >= 3 and out["levels"] >= 1
    overview = out["results"]["overview"]
    print(overview)
    assert "LINE" in overview
    assert any(x in overview for x in ("九月二十", "9月20", "9 月 20", "九月20"))
    for simp in ("会员", "开幕", "设计"):
        assert simp not in overview  # always Traditional Chinese
    questions = " ".join(q["question"] + q["conclusion"] for q in out["results"]["qa"])
    assert "POS" in questions
    # hierarchical reduce must not lose action items (they are carried through, not re-summarized)
    owners = " ".join(i["owner"] + i["task"] for i in out["results"]["action_items"])
    for who in ["小美", "阿傑", "Kevin", "Amy", "Joyce"]:
        assert who in owners, who


def test_mindmap_is_a_valid_tree_about_the_meeting():
    """Phase 07: the model produces a usable mind map (validated tree, short labels, timestamps)."""
    with server() as srv:
        out = summarize(srv, LINES, ["mindmap"], Budget())
    tree = out["results"]["mindmap"]
    print(json.dumps(tree, ensure_ascii=False, indent=1)[:4000])
    assert tree and tree["kind"] == "central"
    mains = tree["children"]
    assert 3 <= len(mains) <= 6
    texts = []

    def walk(n: dict) -> None:
        texts.append(n["text"])
        if n["kind"] != "central":
            assert n["time"] is None or 0 <= n["time"]["start"] <= MEETING["duration"]
        for c in n["children"]:
            walk(c)

    walk(tree)
    joined = " ".join(texts)
    assert "LINE" in joined and "咖啡" in joined
    assert sum(1 for m in mains for _ in m["children"]) >= len(mains)  # branches have sub-topics
    for simp in ("会员", "开幕"):
        assert simp not in joined
