"""Tests for HTML size limits.

Verifies that enforce_html_size honors the cap, raises when oversized
without must_truncate, and truncates cleanly when must_truncate=True.
"""

from __future__ import annotations

import pytest
from app.utils.html_size import (
    HTMLSizeExceeded,
    enforce_html_size,
    get_max_html_bytes,
    truncate_html,
)


def test_within_cap_returns_unchanged():
    assert enforce_html_size("<html>hi</html>", limit=100) == "<html>hi</html>"


def test_at_cap_returns_unchanged():
    s = "x" * 100
    assert enforce_html_size(s, limit=100) == s


def test_over_cap_raises_without_truncation():
    s = "x" * 200
    with pytest.raises(HTMLSizeExceeded) as excinfo:
        enforce_html_size(s, limit=100, must_truncate=False)
    assert excinfo.value.observed == 200
    assert excinfo.value.limit == 100


def test_over_cap_truncates_when_truncation_requested():
    s = "x" * 200
    out = enforce_html_size(s, limit=100, must_truncate=True)
    assert len(out) == 100


def test_exceeded_carries_url_when_supplied():
    with pytest.raises(HTMLSizeExceeded) as excinfo:
        enforce_html_size("x" * 1000, limit=100, url="http://example.com")
    assert excinfo.value.url == "http://example.com"
    assert "http://example.com" in str(excinfo.value)


def test_truncate_html_adds_sentinel():
    s = "x" * 1000
    out = truncate_html(s, cap=100)
    assert len(out) == 100
    assert "truncated by DATAFORGE_MAX_HTML_BYTES" in out


def test_truncate_html_under_cap_is_noop():
    s = "hello"
    assert truncate_html(s, cap=100) == "hello"


def test_get_max_html_bytes_returns_int():
    assert isinstance(get_max_html_bytes(), int)
    assert get_max_html_bytes() > 0
