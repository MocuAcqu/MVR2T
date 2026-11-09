"""Memory readings must be real numbers that move — never a silent 0 (Windows regression 9b3a5a8)."""
from __future__ import annotations

import sys

import pytest

from app.core.procmem import current_rss_mb, peak_rss_mb


@pytest.mark.skipif(sys.platform == "darwin", reason="current RSS not available on macOS without extra packages")
def test_current_rss_increases_after_allocating():
    before = current_rss_mb()
    assert before is not None and before > 10  # a Python process with pytest is never under 10 MB
    block = bytearray(300 * 1024 * 1024)
    for i in range(0, len(block), 4096):  # touch every page so it is really resident
        block[i] = 1
    after = current_rss_mb()
    assert after is not None and after - before > 250, (before, after)
    del block


def test_peak_is_at_least_current():
    peak = peak_rss_mb()
    assert peak > 10
    cur = current_rss_mb()
    if cur is not None:
        assert peak + 1 >= cur
