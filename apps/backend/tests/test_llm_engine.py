"""Phase 06 summary engine without a real model: chunking, prompts, refs → times, hierarchy, llama-server process."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.engines.llm.server import LlamaServer, LlmCancelled, LlmError, ServerOptions
from app.engines.llm.summarize import (
    ALL_TYPES,
    FINAL_SCHEMAS,
    NOTES_SCHEMA,
    REDUCE_SCHEMA,
    Budget,
    Line,
    estimate_tokens,
    mindmap_coverage,
    normalize,
    split_chunks,
    summarize,
)

FIXTURES = Path(__file__).parent / "fixtures"
MINDMAP_REPLY = {
    "title": "中山店开幕会议",
    "children": [
        {"title": "开幕", "refs": [4, 5], "children": [
            {"title": "咖啡机", "refs": [6, 7], "children": [
                {"title": "九月十号确认", "refs": [8], "conclusion": True},
                {"title": "", "refs": [], "conclusion": False},
            ]},
        ]},
        {"title": "", "refs": [1], "children": []},
        {"title": "会员点数", "refs": [60, 999], "children": []},
    ],
}
MEETING = json.loads((FIXTURES / "meeting_zh.json").read_text(encoding="utf-8"))
LINES = [Line(s["id"], s["start"], s["end"], s["text"]) for s in MEETING["segments"]]


@dataclass
class Res:
    content: str
    prompt_tokens: int = 1
    completion_tokens: int = 1
    prompt_ms: float = 1.0
    predicted_ms: float = 1.0
    cached_tokens: int = 0


class FakeLlm:
    """Answers each request with a valid object for the schema it was given and records the prompts."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def chat(self, messages, *, max_tokens, json_schema=None, temperature=0.3):  # noqa: ANN001
        user = messages[-1]["content"]
        self.calls.append((user, json_schema))
        ids = [int(x) for x in __import__("re").findall(r"\[(\d+)\] \d", user)] or [0]
        if json_schema is REDUCE_SCHEMA:
            return Res(json.dumps({"summary": "合并", "points": [{"text": "合并重点", "refs": ids[:1]}]}, ensure_ascii=False))
        if json_schema is NOTES_SCHEMA:
            return Res(json.dumps({
                "summary": f"这一段有 {len(ids)} 句",  # Simplified on purpose
                "points": [{"text": "重点", "refs": ids[:2]}],
                "keywords": ["咖啡"],
                "actions": [{"task": "追踪", "owner": "小美", "due": "", "refs": [ids[0], 9999]}],
                "questions": [],
            }, ensure_ascii=False))
        key = next(iter(json_schema["properties"]))
        if json_schema is FINAL_SCHEMAS["mindmap"]:
            return Res(json.dumps(MINDMAP_REPLY, ensure_ascii=False))
        values = {
            "overview": "这是摘要。 } }",
            "key_points": [{"text": "开幕日期", "refs": [5, 3, 3, -1]}],
            "sections": [{"title": "人力", "bullets": ["正职", ""], "refs": [11]}],
            "topics": [{"title": "会员", "description": "LINE", "refs": []}],
            "keywords": ["中山店", "中山店", " "],
            "action_items": [{"task": "", "owner": "", "due": "", "refs": []}, {"task": "寄出", "owner": "阿杰", "due": "周五", "refs": [17]}],
            "qa": [{"question": "POS?", "conclusion": "尚未定论", "refs": [37]}],
        }
        return Res(json.dumps({key: values[key]}, ensure_ascii=False))


def test_token_estimate_is_conservative_for_chinese_and_english():
    assert estimate_tokens("中山店開幕") >= 5
    assert 2 <= estimate_tokens("hello world") <= 6


def test_chunks_keep_sentences_whole_and_in_order():
    chunks = split_chunks(LINES, 300)
    assert len(chunks) > 3
    assert [ln for c in chunks for ln in c] == LINES


def test_short_transcript_is_summarized_directly_with_shared_prefix():
    llm = FakeLlm()
    out = summarize(llm, LINES, ["qa", "overview", "keywords"], Budget())
    assert out["chunks"] == 1 and out["levels"] == 0
    assert out["types"] == ["overview", "keywords", "qa"]  # canonical order
    prompts = [p for p, _ in llm.calls]
    # same transcript first, instruction last -> llama-server reuses the cached prefix
    prefix = prompts[0].split("任務：")[0]
    assert all(p.startswith(prefix) for p in prompts)
    r = out["results"]
    assert r["overview"] == "這是摘要。"  # Traditional + trailing junk removed
    assert r["keywords"] == ["中山店"]
    assert r["qa"][0]["conclusion"] == "尚未定論"
    assert r["qa"][0]["time"] == {"start": LINES[37].start, "end": LINES[37].end}


def test_refs_are_validated_and_turned_into_times():
    by_id = {ln.id: ln for ln in LINES}
    pts = normalize("key_points", {"key_points": [{"text": "a", "refs": [5, 3, 3, -1, "x"]}]}, by_id)
    assert pts[0]["refs"] == [3, 5]
    assert pts[0]["time"] == {"start": LINES[3].start, "end": LINES[5].end}
    acts = normalize("action_items", {"action_items": [{"task": "", "owner": "", "due": "", "refs": []}]}, by_id)
    assert acts == []  # empty items dropped
    acts = normalize("action_items", {"action_items": [{"task": "討論備案", "owner": "空字串", "due": "未提及", "refs": []}]}, by_id)
    assert acts[0]["owner"] == "" and acts[0]["due"] == ""  # "leave blank" written out as words


def test_long_transcript_uses_map_and_hierarchical_reduce():
    llm = FakeLlm()
    stages: list[str] = []
    budget = Budget(chunk_input=300, notes_input=330, map_output=230, final_output=800)
    out = summarize(llm, LINES, list(ALL_TYPES), budget, progress=lambda p, s, d: stages.append(s))
    assert out["chunks"] > 3 and out["levels"] >= 2  # map + at least one reduce level
    assert any(s is REDUCE_SCHEMA for _, s in llm.calls)
    # reduce only condenses the narrative: every chunk's action item survives to the final prompt
    final_prompt = llm.calls[-1][0]
    assert final_prompt.count("待辦：追") == out["chunks"]
    schemas = [s for _, s in llm.calls]
    n_map = out["chunks"]
    assert all(s is NOTES_SCHEMA for s in schemas[:n_map])
    assert all(s is REDUCE_SCHEMA for s in schemas[n_map:-len(ALL_TYPES)])
    assert schemas[-len(ALL_TYPES):] == [FINAL_SCHEMAS[t] for t in ALL_TYPES]
    assert "正在閱讀逐字稿" in stages and "正在整合重點" in stages and stages[-1] == "完成"
    # final prompts are built from notes, never from the raw transcript
    assert "筆記（依時間順序）" in llm.calls[-1][0]
    assert set(out["results"]) == set(ALL_TYPES)


def test_budget_scales_down_for_small_context():
    b = Budget.for_ctx(4096)
    b.check()
    assert b.chunk_input < Budget().chunk_input


# ---------------------------------------------------------------------------
# llama-server process (fake executable)
# ---------------------------------------------------------------------------


def fake_server(tmp_path: Path, **kw) -> LlamaServer:  # noqa: ANN003
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    return LlamaServer(ServerOptions(FIXTURES / "fake_llama_server.py", model, launcher=(sys.executable,), startup_timeout=20, **kw))


def test_server_waits_for_model_load_then_chats_and_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_LLAMA_MODE", "ok")
    monkeypatch.setenv("FAKE_LLAMA_REPLY", '{"overview": "好"}')
    srv = fake_server(tmp_path)
    with srv:
        pid = srv.pid
        assert srv.load_seconds >= 0.3  # waited through the 503 "loading" phase
        res = srv.chat([{"role": "user", "content": "hi"}], max_tokens=10, json_schema=FINAL_SCHEMAS["overview"])
        assert json.loads(res.content) == {"overview": "好"}
    assert srv.pid is None and pid is not None


def test_server_reports_out_of_memory_in_plain_language(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_LLAMA_MODE", "oom")
    with pytest.raises(LlmError, match="記憶體不足"):
        with fake_server(tmp_path):
            pass


def test_missing_executable_or_model_is_a_clear_error(tmp_path):
    with pytest.raises(LlmError, match="llama-server"):
        LlamaServer(ServerOptions(tmp_path / "nope.exe", tmp_path / "m.gguf")).start()


def test_kill_cancels_a_running_generation_quickly(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_LLAMA_MODE", "slow")
    srv = fake_server(tmp_path)
    with srv:
        threading.Timer(0.5, srv.kill).start()
        started = time.monotonic()
        with pytest.raises(LlmCancelled):
            srv.chat([{"role": "user", "content": "x"}], max_tokens=10, json_schema=FINAL_SCHEMAS["overview"])
        assert time.monotonic() - started < 10


@pytest.mark.skipif(not (sys.platform.startswith("linux") or sys.platform == "win32"), reason="no tie mechanism on this OS")
def test_child_dies_when_the_backend_process_dies(tmp_path):
    """spawn_tied: if the backend crashes, llama-server must not be left running (Windows Job Object / Linux PDEATHSIG)."""
    import subprocess

    from tests.test_lifecycle import pid_alive, wait_dead

    script = (
        "import sys, time, threading\n"
        "from app.core.childproc import spawn_tied\n"
        "p = spawn_tied([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "print(p.pid, flush=True)\n"
        "time.sleep(120)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                              stdout=subprocess.PIPE, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    try:
        assert parent.stdout is not None
        child = int(parent.stdout.readline())
        assert pid_alive(child)
        parent.kill()  # crash: no cleanup code runs
        parent.wait(10)
        assert wait_dead(child, 10), "llama-server-like child survived the backend"
    finally:
        if parent.poll() is None:
            parent.kill()


def test_mindmap_is_a_validated_tree_with_ids_kinds_and_times():
    by_id = {ln.id: ln for ln in LINES}
    tree = normalize("mindmap", MINDMAP_REPLY, by_id)
    assert tree["id"] == "n" and tree["kind"] == "central" and tree["text"] == "中山店開幕會議"
    assert [c["text"] for c in tree["children"]] == ["開幕", "會員點數"]  # empty branch dropped, Traditional
    main = tree["children"][0]
    assert main["id"] == "n-1" and main["kind"] == "main" and main["time"] == {"start": LINES[4].start, "end": LINES[5].end}
    sub = main["children"][0]
    assert sub["kind"] == "sub" and sub["id"] == "n-1-1"
    assert [d["kind"] for d in sub["children"]] == ["conclusion"]  # empty detail dropped
    assert tree["children"][1]["refs"] == [60]  # unknown sentence id removed
    assert normalize("mindmap", {"title": "x", "children": []}, by_id) is None  # nothing to show


class EarlyMindmapLlm(FakeLlm):
    """The first mind map only covers the first few sentences (seen once on Windows); the retry covers everything."""

    def __init__(self, retry_refs: int) -> None:
        super().__init__()
        self.retry_refs = retry_refs
        self.mindmap_temps: list[float] = []

    def chat(self, messages, *, max_tokens, json_schema=None, temperature=0.3):  # noqa: ANN001
        if json_schema is not FINAL_SCHEMAS["mindmap"]:
            return super().chat(messages, max_tokens=max_tokens, json_schema=json_schema, temperature=temperature)
        self.calls.append((messages[-1]["content"], json_schema))
        self.mindmap_temps.append(temperature)
        refs = [2] if len(self.mindmap_temps) == 1 else [self.retry_refs]
        reply = {"title": "会议", "children": [{"title": "开幕", "refs": [1], "children": [{"title": "日期", "refs": refs, "children": []}]}]}
        return Res(json.dumps(reply, ensure_ascii=False))


def test_mindmap_that_only_covers_the_beginning_is_regenerated_once():
    last = LINES[-1].id
    llm = EarlyMindmapLlm(retry_refs=last)
    out = summarize(llm, LINES, ["mindmap"], Budget())
    assert llm.mindmap_temps == [0.3, 0.1]
    assert "必須涵蓋從開頭到結尾" in llm.calls[-1][0]
    assert mindmap_coverage(out["results"]["mindmap"], LINES) == 1.0
    # the retry is no better: keep the first one, and never try a third time
    llm2 = EarlyMindmapLlm(retry_refs=1)
    out2 = summarize(llm2, LINES, ["mindmap"], Budget())
    assert len(llm2.mindmap_temps) == 2
    assert out2["results"]["mindmap"]["children"][0]["children"][0]["refs"] == [2]
    # a mind map that already covers the content is not regenerated
    llm3 = FakeLlm()
    summarize(llm3, LINES, ["mindmap"], Budget())
    assert sum(1 for _, s in llm3.calls if s is FINAL_SCHEMAS["mindmap"]) == 1


def test_mindmap_uses_its_own_output_budget():
    llm = FakeLlm()
    out = summarize(llm, LINES, ["mindmap"], Budget())
    assert out["results"]["mindmap"]["children"]
    b = Budget()
    b.check()
    assert b.mindmap_output > b.final_output
    Budget.for_ctx(4096).check()
