"""逐字稿摘要：切段、提示詞、JSON 結構、階層式整合（PROJECT_SPEC §4-E、§5.5）。

流程：
    逐字稿句子（含時間） ─┬─ 夠短：直接對整份逐字稿產生每一種摘要
                         └─ 太長：依 token 預算切成多段 → 每段產生「段落筆記」(map)
                                  → 筆記太多時再分組整合 (reduce，可多層) → 對最終筆記產生每一種摘要
每一種摘要類型是一次獨立的請求，回應受 JSON schema 約束（llama.cpp 以 grammar 保證格式）。
同一份輸入放在提示詞最前面，後面才放類型專屬的指示，讓 llama-server 的 prompt cache 共用前段，只算一次。

時間戳記：模型不寫時間，而是引用句子編號（refs）；程式再把編號換回原始時間範圍，避免模型編造時間。
繁體中文：模型常輸出簡體，所有文字最後一律以 OpenCC s2twp 轉成繁體（台灣用語）。
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.engines.asr.text import to_traditional

SummaryType = Literal["overview", "key_points", "notes", "topics", "keywords", "action_items", "qa"]
ALL_TYPES: tuple[SummaryType, ...] = ("overview", "key_points", "notes", "topics", "keywords", "action_items", "qa")
TYPE_LABELS: dict[SummaryType, str] = {
    "overview": "全文摘要",
    "key_points": "重點整理",
    "notes": "條列式筆記",
    "topics": "主題分類",
    "keywords": "關鍵字",
    "action_items": "行動事項",
    "qa": "問題與結論",
}


class Chat(Protocol):
    def chat(
        self, messages: list[dict[str, str]], *, max_tokens: int, json_schema: dict[str, Any] | None = None, temperature: float = 0.3
    ) -> Any: ...


@dataclass(frozen=True)
class Line:
    """一句逐字稿。id 是在整份逐字稿中的編號（給模型引用）。"""

    id: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Budget:
    """token 預算（預設對應 8192 context）。"""

    ctx: int = 8192
    chunk_input: int = 3000  # 每段逐字稿最多幾個 token
    notes_input: int = 4800  # 最終摘要時，筆記最多幾個 token（超過才做階層式整合）
    map_output: int = 1600
    final_output: int = 1600

    @classmethod
    def for_ctx(cls, ctx: int) -> Budget:
        """依 context 長度縮放（規格 §5.3 建議 4096–8192；記憶體不足時可降低 MVR2T_LLM_CTX）。"""
        if ctx >= 8192:
            return cls(ctx=ctx)
        scale = ctx / 8192
        return cls(
            ctx=ctx,
            chunk_input=int(3000 * scale),
            notes_input=int(4800 * scale),
            map_output=max(900, int(1600 * scale)),
            final_output=max(900, int(1600 * scale)),
        )

    def check(self) -> None:
        overhead = 700  # 系統提示與指示
        if self.chunk_input + self.map_output + overhead > self.ctx or self.notes_input + self.final_output + overhead > self.ctx:
            raise ValueError("budget exceeds context")


# ---------------------------------------------------------------------------
# token 估計與切段
# ---------------------------------------------------------------------------

_CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]")


def estimate_tokens(text: str) -> int:
    """保守估計（寧可高估）：中日韓字元各算 1 token，其他字元約 3.2 個字元 1 token。"""
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk + 2) // 3 + 1


def fmt_time(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_lines(lines: Sequence[Line]) -> str:
    return "\n".join(f"[{ln.id}] {fmt_time(ln.start)} {ln.text}" for ln in lines)


def split_chunks(lines: Sequence[Line], max_tokens: int) -> list[list[Line]]:
    """依 token 預算切段，句子不拆開；單句超過預算時獨立成段（極少見，通常是辨識成一長句）。"""
    chunks: list[list[Line]] = []
    cur: list[Line] = []
    used = 0
    for ln in lines:
        cost = estimate_tokens(f"[{ln.id}] {fmt_time(ln.start)} {ln.text}") + 1
        if cur and used + cost > max_tokens:
            chunks.append(cur)
            cur, used = [], 0
        cur.append(ln)
        used += cost
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------------------
# JSON schema
# ---------------------------------------------------------------------------

_REFS = {"type": "array", "items": {"type": "integer"}, "maxItems": 4}


def _s(max_chars: int) -> dict[str, Any]:
    """字串長度上限：llama.cpp 會把它寫進 grammar，保證輸出不會長到被 max_tokens 截斷成不完整的 JSON。
    （2026-11-09 沙盒：沒有上限時，分段筆記的 summary 寫到超過 900 tokens 被截斷。）"""
    return {"type": "string", "maxLength": max_chars}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _list(item: dict[str, Any], max_items: int) -> dict[str, Any]:
    return {"type": "array", "items": item, "maxItems": max_items}


# 每種類型最壞情況的輸出長度都控制在 final_output（1600 tokens）以內
FINAL_SCHEMAS: dict[SummaryType, dict[str, Any]] = {
    "overview": _obj({"overview": _s(700)}),
    "key_points": _obj({"key_points": _list(_obj({"text": _s(110), "refs": _REFS}), 10)}),
    "notes": _obj({"sections": _list(_obj({"title": _s(24), "bullets": _list(_s(70), 6), "refs": _REFS}), 8)}),
    "topics": _obj({"topics": _list(_obj({"title": _s(24), "description": _s(110), "refs": _REFS}), 8)}),
    "keywords": _obj({"keywords": _list(_s(16), 15)}),
    "action_items": _obj({"action_items": _list(_obj({"task": _s(70), "owner": _s(16), "due": _s(20), "refs": _REFS}), 12)}),
    "qa": _obj({"qa": _list(_obj({"question": _s(60), "conclusion": _s(90), "refs": _REFS}), 10)}),
}

# 分段筆記：最壞情況約 1300 個中文字，小於 map_output
NOTES_SCHEMA = _obj({
    "summary": _s(260),
    "points": _list(_obj({"text": _s(80), "refs": _REFS}), 8),
    "keywords": _list(_s(12), 10),
    "actions": _list(_obj({"task": _s(60), "owner": _s(12), "due": _s(16), "refs": _REFS}), 6),
    "questions": _list(_obj({"question": _s(50), "conclusion": _s(70), "refs": _REFS}), 5),
})

# ---------------------------------------------------------------------------
# 提示詞
# ---------------------------------------------------------------------------

SYSTEM = (
    "你是嚴謹的會議與課程記錄助理，負責整理語音辨識產生的逐字稿。\n"
    "規則：\n"
    "1. 一律使用繁體中文（台灣用語）回答，但人名、品牌、產品、程式碼等專有名詞保留原文。\n"
    "2. 只根據提供的內容整理，不可加入內容中沒有的事實、數字、人名或日期；不確定的就省略。\n"
    "3. 逐字稿是語音辨識結果，可能有錯字或口語贅詞，請理解原意後用通順的書面語整理。\n"
    "4. 每一行開頭的 [數字] 是句子編號；refs 欄位填入支持該項目的句子編號（1～3 個），只能使用出現過的編號。\n"
    "5. 依照指定的 JSON 格式輸出，不要輸出其他文字。"
)

FINAL_INSTRUCTIONS: dict[SummaryType, str] = {
    "overview": "請寫一段全文摘要（150～300 字），說明這份內容在談什麼、主要的結論或決定是什麼。用完整的句子，不要條列。",
    "key_points": "請整理 5～10 個最重要的重點，依內容出現的順序排列。每個重點一句話，具體寫出結論或數字，並附上 refs。",
    "notes": "請整理成條列式筆記：依內容分成 3～8 個小節，每節一個簡短標題與 2～6 個條列，並附上該節主要對應的 refs。",
    "topics": "請把內容歸納成 3～8 個主題，每個主題有標題與一兩句說明，並附上 refs。",
    "keywords": "請列出 5～15 個關鍵字或專有名詞（人名、地名、產品、重要概念），每個 2～10 字，不要重複。",
    "action_items": (
        "請列出所有明確的行動事項（有人答應要做、或被指派要做的事；只是討論、尚未指派的不算）。"
        "owner 填負責人、due 填期限，內容沒有提到就讓該欄位保持空白，並附上 refs。沒有任何行動事項就回傳空陣列。"
    ),
    "qa": (
        "請列出內容中討論的問題與結論：問題寫成問句；已有結論就寫結論，"
        "沒有結論就寫「尚未定論」並簡述目前的看法。附上 refs。沒有就回傳空陣列。"
    ),
}

MAP_INSTRUCTION = (
    "這是一份長逐字稿的其中一段。請為這一段做筆記：summary（3～6 句）、points（這段的重點，3～8 個）、"
    "keywords、actions（明確的行動事項，負責人與期限沒提到就讓欄位保持空白）、questions（討論的問題與結論，沒有結論寫「尚未定論」）。"
    "沒有的項目回傳空陣列。"
)

REDUCE_INSTRUCTION = (
    "以上是同一份內容依時間順序排列的多段筆記。請把各部分的摘要與重點整合成一份：summary 寫 4～8 句，"
    "points 保留所有具體的結論、決定與數字（合併重複的），refs 保留原本的句子編號。各部分的內容都要涵蓋，不可只寫前面幾部分。"
)

# 階層式整合只濃縮「敘述」（摘要與重點）；行動事項、問題與關鍵字原樣保留到最後，避免逐層整合時遺失
# （2026-11-09 沙盒：連同待辦一起整合三層後，5 個負責人只剩 3 個）。
REDUCE_SCHEMA = _obj({
    "summary": _s(360),
    "points": _list(_obj({"text": _s(80), "refs": _REFS}), 12),
})


def _transcript_block(lines: Sequence[Line], part: tuple[int, int] | None = None) -> str:
    head = f"逐字稿（第 {part[0]} / {part[1]} 段）：" if part else "逐字稿："
    return f"{head}\n{format_lines(lines)}"


def _notes_block(notes: Sequence[dict[str, Any]]) -> str:
    return "筆記（依時間順序）：\n" + "\n\n".join(_render_notes(n, i + 1) for i, n in enumerate(notes))


def _render_notes(n: dict[str, Any], idx: int) -> str:
    """把一份筆記轉成精簡文字（比 JSON 省 token），refs 以 [12,13] 形式保留。"""
    def refs(r: Sequence[int]) -> str:
        return f" [{','.join(str(x) for x in r)}]" if r else ""

    out = [f"### 第 {idx} 部分", f"摘要：{n.get('summary', '')}"]
    for p in n.get("points", []):
        out.append(f"- 重點：{p['text']}{refs(p.get('refs', []))}")
    for a in n.get("actions", []):
        extra = "；".join(x for x in (f"負責：{a.get('owner')}" if a.get("owner") else "", f"期限：{a.get('due')}" if a.get("due") else "") if x)
        out.append(f"- 待辦：{a['task']}{'（' + extra + '）' if extra else ''}{refs(a.get('refs', []))}")
    for q in n.get("questions", []):
        out.append(f"- 問題：{q['question']} → {q['conclusion']}{refs(q.get('refs', []))}")
    if n.get("keywords"):
        out.append("關鍵字：" + "、".join(n["keywords"]))
    return "\n".join(out)


def _messages(context: str, instruction: str) -> list[dict[str, str]]:
    # 共用的內容放前面（prompt cache），類型專屬的指示放最後
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{context}\n\n任務：{instruction}"}]


# ---------------------------------------------------------------------------
# 後處理
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except ValueError as e:
        raise ValueError(f"model returned invalid JSON: {text[:200]!r}") from e
    if not isinstance(value, dict):
        raise ValueError("model returned non-object JSON")
    return value


def _clean_refs(refs: Any, valid: set[int]) -> list[int]:
    if not isinstance(refs, list):
        return []
    out: list[int] = []
    for r in refs:
        if isinstance(r, int) and r in valid and r not in out:
            out.append(r)
    return sorted(out)[:4]


_TRAILING_JUNK = re.compile(r"[\s}\]]+$")


def _clean_text(text: str) -> str:
    """去掉模型偶爾在字串結尾多寫的 `} }`、`]` 之類的殘渣（JSON 格式本身已由 grammar 保證）。"""
    return _TRAILING_JUNK.sub("", text.strip()).strip()


def _tw(value: Any) -> Any:
    """所有字串轉繁體（台灣用語），保留結構。"""
    if isinstance(value, str):
        return to_traditional(_clean_text(value))
    if isinstance(value, list):
        return [_tw(v) for v in value]
    if isinstance(value, dict):
        return {k: (_tw(v) if k != "refs" else v) for k, v in value.items()}
    return value


# 模型偶爾把「留空」寫成文字（2026-11-09 Qwen3-4B 實測：owner 填「空字串」）
_PLACEHOLDERS = frozenset({"空字串", "空白", "無", "没有", "沒有", "未提及", "未提到", "不明", "未知", "N/A", "n/a", "none", "None", "null", "-", "—"})


def _blank_placeholder(text: str) -> str:
    return "" if text.strip() in _PLACEHOLDERS else text


def _span(refs: list[int], by_id: dict[int, Line]) -> dict[str, float] | None:
    if not refs:
        return None
    return {"start": by_id[refs[0]].start, "end": by_id[refs[-1]].end}


def normalize(kind: SummaryType, raw: dict[str, Any], by_id: dict[int, Line]) -> Any:
    """驗證模型輸出、清理 refs、轉繁體，並把 refs 換成時間範圍（time）。"""
    valid = set(by_id)
    data = _tw(raw)

    def with_time(item: dict[str, Any]) -> dict[str, Any]:
        refs = _clean_refs(item.get("refs"), valid)
        return {**{k: v for k, v in item.items() if k != "refs"}, "refs": refs, "time": _span(refs, by_id)}

    def nonempty(items: Any, key: str) -> list[dict[str, Any]]:
        return [with_time(i) for i in (items if isinstance(items, list) else []) if isinstance(i, dict) and str(i.get(key, "")).strip()]

    if kind == "overview":
        return str(data.get("overview", "")).strip()
    if kind == "key_points":
        return nonempty(data.get("key_points"), "text")
    if kind == "notes":
        sections = nonempty(data.get("sections"), "title")
        for s in sections:
            s["bullets"] = [b for b in s.get("bullets", []) if isinstance(b, str) and b.strip()]
        return sections
    if kind == "topics":
        return nonempty(data.get("topics"), "title")
    if kind == "keywords":
        seen: list[str] = []
        for k in data.get("keywords", []) if isinstance(data.get("keywords"), list) else []:
            if isinstance(k, str) and k.strip() and k.strip() not in seen:
                seen.append(k.strip())
        return seen
    if kind == "action_items":
        items = nonempty(data.get("action_items"), "task")
        for a in items:
            a["owner"] = _blank_placeholder(str(a.get("owner", "")))
            a["due"] = _blank_placeholder(str(a.get("due", "")))
        return items
    if kind == "qa":
        return nonempty(data.get("qa"), "question")
    raise ValueError(kind)


def _clean_notes(raw: dict[str, Any], valid: set[int]) -> dict[str, Any]:
    """map / reduce 的筆記：清理 refs，保持精簡（中間結果不轉繁體，最後一步才轉）。"""
    def items(key: str, text_key: str) -> list[dict[str, Any]]:
        out = []
        for i in raw.get(key, []) if isinstance(raw.get(key), list) else []:
            if isinstance(i, dict) and str(i.get(text_key, "")).strip():
                out.append({**i, "refs": _clean_refs(i.get("refs"), valid)})
        return out

    return {
        "summary": str(raw.get("summary", "")).strip(),
        "points": items("points", "text"),
        "keywords": [k for k in raw.get("keywords", []) if isinstance(k, str) and k.strip()] if isinstance(raw.get("keywords"), list) else [],
        "actions": items("actions", "task"),
        "questions": items("questions", "question"),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

Progress = Callable[[float, str, str], None]  # (0~1, 步驟, 細節)


@dataclass
class Plan:
    chunks: list[list[Line]]
    types: list[SummaryType]

    @property
    def direct(self) -> bool:
        return len(self.chunks) <= 1

    @property
    def steps(self) -> int:
        """估計總步數（顯示進度用）：每段 1 + 整合（估計）+ 每種類型 1。"""
        if self.direct:
            return len(self.types)
        reduce_estimate = max(0, (len(self.chunks) - 1) // 4)
        return len(self.chunks) + reduce_estimate + len(self.types)


def plan(lines: Sequence[Line], types: Sequence[SummaryType], budget: Budget) -> Plan:
    budget.check()
    ordered = [t for t in ALL_TYPES if t in set(types)]
    if not ordered:
        raise ValueError("no summary types")
    chunks = split_chunks(lines, budget.chunk_input) if lines else []
    return Plan(chunks=chunks, types=ordered)


def _call_json(llm: Chat, messages: list[dict[str, str]], schema: dict[str, Any], max_tokens: int) -> tuple[dict[str, Any], Any]:
    """呼叫一次；JSON 解析失敗（字串有長度上限後應不會發生）時以較低溫度、加倍上限重試一次。"""
    res = llm.chat(messages, max_tokens=max_tokens, json_schema=schema)
    try:
        return _parse_json(res.content), res
    except ValueError:
        res = llm.chat(messages, max_tokens=max_tokens * 2, json_schema=schema, temperature=0.1)
        return _parse_json(res.content), res


def summarize(
    llm: Chat,
    lines: Sequence[Line],
    types: Sequence[SummaryType],
    budget: Budget = Budget(),
    progress: Progress = lambda *_: None,
    stats: list[Any] | None = None,
) -> dict[str, Any]:
    """回傳 {"types": [...], "results": {type: data}, "chunks": n, "levels": n}。"""
    p = plan(lines, types, budget)
    by_id = {ln.id: ln for ln in lines}
    valid = set(by_id)
    total = max(1, p.steps)
    done = 0

    def step(stage: str, detail: str) -> None:
        progress(min(0.99, done / total), stage, detail)

    def record(res: Any) -> None:
        if stats is not None:
            stats.append(res)

    if p.direct:
        context = _transcript_block(lines)
        levels = 0
    else:
        notes: list[dict[str, Any]] = []
        n = len(p.chunks)
        for i, chunk in enumerate(p.chunks):
            step("正在閱讀逐字稿", f"第 {i + 1} / {n} 段")
            raw, res = _call_json(llm, _messages(_transcript_block(chunk, (i + 1, n)), MAP_INSTRUCTION), NOTES_SCHEMA, budget.map_output)
            record(res)
            notes.append(_clean_notes(raw, valid))
            done += 1
        levels = 1
        # 筆記總長超過預算時，把相鄰的筆記兩兩（或更多）整合，必要時多層（階層式摘要，§5.5）
        group_budget = budget.notes_input - budget.map_output  # 一次整合的輸入，留空間給輸出
        while estimate_tokens(_notes_block(notes)) > budget.notes_input and len(notes) > 1:
            groups: list[list[dict[str, Any]]] = []
            cur: list[dict[str, Any]] = []
            for nt in notes:
                if len(cur) >= 2 and estimate_tokens(_notes_block([*cur, nt])) > group_budget:
                    groups.append(cur)
                    cur = []
                cur.append(nt)
            groups.append(cur)
            merged: list[dict[str, Any]] = []
            for gi, g in enumerate(groups):
                step("正在整合重點", f"第 {levels} 層，第 {gi + 1} / {len(groups)} 組")
                if len(g) == 1:
                    merged.append(g[0])
                    continue
                raw, res = _call_json(llm, _messages(_notes_block(g), REDUCE_INSTRUCTION), REDUCE_SCHEMA, budget.map_output)
                record(res)
                narrative = _clean_notes(raw, valid)
                merged.append({
                    "summary": narrative["summary"],
                    "points": narrative["points"],
                    "keywords": list(dict.fromkeys(k for nt in g for k in nt["keywords"]))[:30],
                    "actions": [a for nt in g for a in nt["actions"]],
                    "questions": [q for nt in g for q in nt["questions"]],
                })
                done += 1
            total = max(total, done + len(p.types) + 1)
            if len(merged) == len(notes):  # 無法再縮短（只剩待辦與問題本身就很長）：直接用
                break
            notes = merged
            levels += 1
        context = _notes_block(notes)

    results: dict[str, Any] = {}
    for t in p.types:
        step("正在產生摘要", TYPE_LABELS[t])
        raw, res = _call_json(llm, _messages(context, FINAL_INSTRUCTIONS[t]), FINAL_SCHEMAS[t], budget.final_output)
        record(res)
        results[t] = normalize(t, raw, by_id)
        done += 1
    progress(1.0, "完成", "")
    return {"types": list(p.types), "results": results, "chunks": len(p.chunks), "levels": levels}
