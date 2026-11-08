"""逐字稿的文字與時間處理（純函式，不需要模型即可測試）。

流程中的位置：
    ASR（每段文字，簡體）→ 對齊模型（每個字／詞的時間，以「原始簡體文字」對齊才最準）
    → build_sentences()：依標點切句，並用字／詞時間決定每句的起訖
    → 加上段落在原始檔案中的起點（offset）→ dedupe_overlaps()：硬切重疊區只保留一次
    → to_traditional()：整句轉繁體（台灣用語），轉換可能改變字數，所以只在「句」層級轉換

時間單位一律為秒；回傳的時間都已四捨五入到毫秒。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

Timing = Literal["aligned", "estimated"]

# 句末標點（中英）。逗號不切，避免字幕過碎。
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;…])\s*|(?<=[.])\s+(?=[A-Z0-9\"'“‘(（])")
_WORD_CHARS = re.compile(r"[\w]", re.UNICODE)

CHINESE_LANGUAGES = frozenset({"Chinese", "Cantonese"})


@dataclass(frozen=True)
class Unit:
    """對齊模型輸出的最小單位（中文為單字，英文為單詞），時間相對於該段音訊。"""

    text: str
    start: float
    end: float


@dataclass
class Sentence:
    text: str
    start: float
    end: float
    timing: Timing
    units: list[Unit] = field(default_factory=list)


# 英文縮寫後的句點不是句尾（Mr. Smith、e.g. this）
_ABBREVIATIONS = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "vs", "etc", "e.g", "i.e", "u.s", "u.k", "no", "fig", "inc", "ltd", "co"}
)


def split_sentences(text: str) -> list[str]:
    """依句末標點切句；保留標點，去除空白句。"""
    parts = [p.strip() for p in _SENTENCE_END.split(text.strip())]
    parts = [p for p in parts if p]
    merged: list[str] = []
    for p in parts:
        if merged:
            last_word = merged[-1].rsplit(" ", 1)[-1].rstrip(".").lower()
            if merged[-1].endswith(".") and last_word in _ABBREVIATIONS:
                merged[-1] = f"{merged[-1]} {p}"
                continue
        merged.append(p)
    return merged


def _norm(s: str) -> str:
    """比對用：只留文字與數字並轉小寫（對齊模型輸出的單位不含標點）。"""
    return "".join(ch.lower() for ch in s if _WORD_CHARS.match(ch))


def _r(x: float) -> float:
    return round(max(0.0, x), 3)


def build_sentences(text: str, units: list[Unit] | None, duration: float) -> list[Sentence]:
    """把一段的文字切句並配上時間。

    有 units（已對齊）：依序把每個單位對應到它所在的句子，句子時間 = 第一個單位起點 ～ 最後一個單位終點。
    沒有 units（不支援的語言或沒有對齊模型）：依字數比例估計時間，標記為 estimated。
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    if not units:
        weights = [max(1, len(_norm(s))) for s in sentences]
        total = sum(weights)
        out, pos = [], 0.0
        for s, w in zip(sentences, weights):
            nxt = pos + duration * w / total
            out.append(Sentence(s, _r(pos), _r(nxt), "estimated"))
            pos = nxt
        out[-1].end = _r(duration)
        return out

    # 將每個單位對應到句子：在「去掉標點的整段文字」中依序尋找單位文字。
    sent_norm = [_norm(s) for s in sentences]
    bounds, acc = [], 0
    for n in sent_norm:
        acc += len(n)
        bounds.append(acc)  # 每句在正規化字串中的結束位置
    joined = "".join(sent_norm)
    buckets: list[list[Unit]] = [[] for _ in sentences]
    cursor, current = 0, 0
    for u in units:
        key = _norm(u.text)
        idx = joined.find(key, cursor) if key else -1
        if idx >= 0:
            cursor = idx + len(key)
            while current < len(bounds) - 1 and idx >= bounds[current]:
                current += 1
        buckets[current].append(u)

    out: list[Sentence] = []
    for s, bucket in zip(sentences, buckets):
        if bucket:
            out.append(Sentence(s, _r(min(u.start for u in bucket)), _r(max(u.end for u in bucket)), "aligned", bucket))
        else:
            out.append(Sentence(s, -1.0, -1.0, "estimated"))

    # 沒有對應到任何單位的句子（少見）：夾在前後句之間
    for i, s in enumerate(out):
        if s.start < 0:
            prev_end = next((o.end for o in reversed(out[:i]) if o.start >= 0), 0.0)
            next_start = next((o.start for o in out[i + 1 :] if o.start >= 0), duration)
            s.start, s.end = _r(prev_end), _r(max(prev_end, next_start))
    # 時間只增不減（對齊偶爾有微小倒退）
    for a, b in zip(out, out[1:]):
        if b.start < a.start:
            b.start = a.start
        b.end = max(b.end, b.start)
    return out


def shift(sentences: list[Sentence], offset: float) -> list[Sentence]:
    """把段內時間加上段落在原始檔案中的起點。"""
    return [
        Sentence(
            s.text,
            _r(s.start + offset),
            _r(s.end + offset),
            s.timing,
            [Unit(u.text, _r(u.start + offset), _r(u.end + offset)) for u in s.units],
        )
        for s in sentences
    ]


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")
_TRAILING_PUNCT = re.compile(r"[。！？!?；;…，,、.\s]+$")


def _join_units(units: list[Unit]) -> str:
    """中日韓單字直接相連；其他語言以空白分隔單詞。"""
    if all(_CJK.fullmatch(u.text) for u in units):
        return "".join(u.text for u in units)
    return " ".join(u.text for u in units)


def _trim(sent: Sentence, lo: float, hi: float) -> Sentence | None:
    """只保留起點落在 [lo, hi) 的部分。"""
    if not sent.units:
        # 沒有字詞時間：與保留範圍有交集就保留（寧可邊界重複約 1 秒，也不遺失內容）
        return sent if sent.end > lo and sent.start < hi else None
    keep = [u for u in sent.units if lo <= u.start < hi]
    if not keep:
        return None
    if len(keep) == len(sent.units):
        return sent
    text = _join_units(keep)
    if keep[-1] is sent.units[-1]:  # 句尾仍在 → 保留原本的句末標點
        m = _TRAILING_PUNCT.search(sent.text)
        text += m.group(0).strip() if m else ""
    return Sentence(text, keep[0].start, keep[-1].end, sent.timing, keep)


def dedupe_overlaps(per_segment: list[tuple[float, float, list[Sentence]]]) -> list[Sentence]:
    """合併各段（時間已是原始時間軸）。

    硬切的段落會與下一段重疊 overlap 秒，重疊區的內容兩段都會辨識到。以重疊區中點為界，
    「逐字／詞」決定歸屬：前一段只留起點在中點之前的字詞，後一段只留起點在中點（含）之後的字詞，
    被裁掉一部分的句子以剩下的字詞重組文字。如此每個字詞只出現一次，且不會遺失跨越邊界的內容。
    在停頓處切的段落沒有重疊，完全不受影響。
    """
    merged: list[Sentence] = []
    for i, (start, end, sents) in enumerate(per_segment):
        lo = float("-inf")
        hi = float("inf")
        if i > 0:
            prev_end = per_segment[i - 1][1]
            if start < prev_end:
                lo = (start + prev_end) / 2
        if i + 1 < len(per_segment):
            nxt_start = per_segment[i + 1][0]
            if nxt_start < end:
                hi = (nxt_start + end) / 2
        for s in sents:
            t = _trim(s, lo, hi)
            if t is not None:
                merged.append(t)
    return merged


@lru_cache(maxsize=1)
def _converter():  # pragma: no cover - 簡單包裝
    import opencc

    return opencc.OpenCC("s2twp")


def to_traditional(text: str) -> str:
    """簡體 → 繁體（台灣用語，例如 软件→軟體、视频→影片）。"""
    return _converter().convert(text)
