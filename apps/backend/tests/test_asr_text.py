"""Phase 05: transcript text/timing logic (pure functions, no model needed)."""
from __future__ import annotations

import pytest

from app.engines.asr.text import (
    Sentence,
    Unit,
    build_sentences,
    dedupe_overlaps,
    shift,
    split_sentences,
    to_traditional,
)


def test_split_sentences_chinese_and_english():
    assert split_sentences("今天天氣很好。我們出去吧！好嗎？") == ["今天天氣很好。", "我們出去吧！", "好嗎？"]
    assert split_sentences("Hello there. How are you? Fine!") == ["Hello there.", "How are you?", "Fine!"]
    # decimal points and abbreviations followed by lowercase are not sentence ends
    assert split_sentences("It costs 3.5 dollars. ok") == ["It costs 3.5 dollars. ok"]
    assert split_sentences("Mr. Quilter is here.") == ["Mr. Quilter is here."]
    assert split_sentences("Ask Dr. Lee. Then go, e.g. Home now.") == ["Ask Dr. Lee.", "Then go, e.g. Home now."]
    assert split_sentences("  ") == []


def _units(chars: str, step: float = 0.2, start: float = 0.0) -> list[Unit]:
    return [Unit(c, round(start + i * step, 3), round(start + (i + 1) * step, 3)) for i, c in enumerate(chars)]


def test_build_sentences_uses_aligned_units():
    text = "今天天氣好。我們出去。"
    units = _units("今天天氣好我們出去", step=0.25)
    out = build_sentences(text, units, duration=3.0)
    assert [s.text for s in out] == ["今天天氣好。", "我們出去。"]
    assert (out[0].start, out[0].end) == (0.0, 1.25)
    assert (out[1].start, out[1].end) == (1.25, 2.25)
    assert all(s.timing == "aligned" for s in out)
    assert len(out[0].units) == 5 and len(out[1].units) == 4


def test_build_sentences_english_words_with_punctuation():
    text = "Mr. Quilter is here. He is glad."
    words = ["Mr", "Quilter", "is", "here", "He", "is", "glad"]
    units = [Unit(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(words)]
    out = build_sentences(text, units, duration=4.0)
    assert [s.text for s in out] == ["Mr. Quilter is here.", "He is glad."]
    assert out[0].end == 1.9 and out[1].start == 2.0


def test_build_sentences_estimates_when_not_aligned():
    out = build_sentences("短句。這是一個比較長的句子。", None, duration=9.0)
    assert [s.timing for s in out] == ["estimated", "estimated"]
    assert out[0].start == 0 and out[-1].end == 9.0
    assert out[0].end == pytest.approx(9.0 * 2 / 12, abs=0.001)  # 2 of 12 characters


def test_unmatched_sentence_is_placed_between_neighbours():
    out = build_sentences("甲乙。丙丁。戊己。", [Unit("甲", 0, 0.5), Unit("乙", 0.5, 1), Unit("戊", 3, 3.5), Unit("己", 3.5, 4)], 5.0)
    assert [(s.start, s.end) for s in out] == [(0.0, 1.0), (1.0, 3.0), (3.0, 4.0)]
    assert out[1].timing == "estimated"


def test_times_never_go_backwards():
    out = build_sentences("甲。乙。", [Unit("甲", 1.0, 1.5), Unit("乙", 0.9, 1.2)], 2.0)
    assert out[1].start >= out[0].start and out[1].end >= out[1].start


def test_shift_adds_segment_offset_to_sentences_and_units():
    s = build_sentences("甲乙。", [Unit("甲", 0.1, 0.3), Unit("乙", 0.3, 0.6)], 1.0)
    shifted = shift(s, 58.613)
    assert (shifted[0].start, shifted[0].end) == (58.713, 59.213)
    assert shifted[0].units[1] == Unit("乙", 58.913, 59.213)


def _sent(text: str, start: float, end: float | None = None) -> Sentence:
    return Sentence(text, start, end if end is not None else start + 0.5, "estimated")


def _aligned(chars: str, start: float, step: float, text: str | None = None) -> Sentence:
    units = [Unit(c, round(start + i * step, 3), round(start + (i + 1) * step, 3)) for i, c in enumerate(chars)]
    return Sentence(text or chars + "。", units[0].start, units[-1].end, "aligned", units)


def test_dedupe_overlaps_word_level_keeps_every_word_exactly_once():
    # hard cut: segment 0 = 0-30, segment 1 = 29-59 -> overlap 29-30, boundary 29.5.
    # The speaker says 甲乙丙丁戊己 from 28.0 to 31.0 (0.5 s each); both segments hear part of it.
    seg0 = (0.0, 30.0, [_aligned("早安", 1.0, 0.5), _aligned("甲乙丙丁", 28.0, 0.5, "甲乙丙丁")])  # cut mid-sentence
    seg1 = (29.0, 59.0, [_aligned("丙丁戊己", 29.0, 0.5), _aligned("晚安", 40.0, 0.5)])
    out = dedupe_overlaps([seg0, seg1])
    assert [s.text for s in out] == ["早安。", "甲乙丙", "丁戊己。", "晚安。"]
    words = [u.text for s in out for u in s.units]
    assert words == list("早安甲乙丙丁戊己晚安")  # nothing lost, nothing duplicated
    assert out[2].start == 29.5  # the continuation is kept (old sentence-level rule dropped it)


def test_dedupe_overlaps_english_rebuilds_text_from_words():
    s0 = Sentence("so we begin", 28.6, 29.9, "aligned", [Unit("so", 28.6, 28.9), Unit("we", 29.0, 29.3), Unit("begin", 29.6, 29.9)])
    s1 = Sentence("begin the lesson.", 29.6, 31.0, "aligned", [Unit("begin", 29.6, 29.9), Unit("the", 30.0, 30.2), Unit("lesson", 30.3, 31.0)])
    out = dedupe_overlaps([(0.0, 30.0, [s0]), (29.0, 59.0, [s1])])
    assert [s.text for s in out] == ["so we", "begin the lesson."]


def test_dedupe_overlaps_without_word_times_prefers_duplicate_over_loss():
    seg0 = (0.0, 30.0, [_sent("a", 1.0), _sent("tail", 28.0, 29.8)])
    seg1 = (29.0, 59.0, [_sent("head", 29.0, 33.0), _sent("b", 40.0)])
    assert [s.text for s in dedupe_overlaps([seg0, seg1])] == ["a", "tail", "head", "b"]


def test_dedupe_overlaps_silence_cut_keeps_everything():
    seg0 = (0.0, 28.0, [_sent("a", 1.0), _sent("b", 27.9)])
    seg1 = (28.0, 58.0, [_sent("c", 28.0)])
    assert [s.text for s in dedupe_overlaps([seg0, seg1])] == ["a", "b", "c"]


def test_to_traditional_taiwan_phrasing():
    assert to_traditional("人工智能软件需要内存和视频网络。") == "人工智慧軟體需要記憶體和影片網路。"
    assert to_traditional("Hello 123") == "Hello 123"
