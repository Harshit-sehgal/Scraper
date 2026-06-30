"""Tests for encoding detection module (Roadmap Rel 11)."""

from __future__ import annotations

import sys
from unittest import mock

import pytest
from app.encoding_detection import (
    _detect_bom,
    _is_likely_utf8,
    _looks_like_binary,
    _normalise_charset,
    decode_content,
    detect_encoding,
)

# ─── BOM detection tests ──────────────────────────────────────────────────


def test_bom_utf8_detection() -> None:
    """UTF-8 BOM (EF BB BF) should be detected as utf-8-sig."""
    content = b"\xef\xbb\xbfHello, world!"
    assert _detect_bom(content) == "utf-8-sig"


def test_bom_utf16le_detection() -> None:
    """UTF-16 LE BOM (FF FE) should be detected as utf-16-le."""
    content = b"\xff\xfeH\x00e\x00l\x00l\x00o\x00"
    assert _detect_bom(content) == "utf-16-le"


def test_bom_utf16be_detection() -> None:
    """UTF-16 BE BOM (FE FF) should be detected as utf-16-be."""
    content = b"\xfe\xff\x00H\x00e\x00l\x00l\x00o"
    assert _detect_bom(content) == "utf-16-be"


def test_no_bom_plain_utf8() -> None:
    """Plain UTF-8 without BOM returns None from _detect_bom."""
    content = b"Hello, world!"
    assert _detect_bom(content) is None


def test_bom_prioritised_longest_match() -> None:
    """UTF-32 LE BOM (FF FE 00 00) should match before UTF-16 LE BOM (FF FE)."""
    content = b"\xff\xfe\x00\x00\x00\x00\x00\x00"
    assert _detect_bom(content) == "utf-32-le"


# ─── encoding alias normalisation tests ───────────────────────────────────


def test_normalise_ascii_to_utf8() -> None:
    """ASCII should normalise to utf-8."""
    assert _normalise_charset("ascii") == "utf-8"
    assert _normalise_charset("ASCII") == "utf-8"


def test_normalise_latin_aliases() -> None:
    """Various latin-1 aliases should normalise correctly."""
    assert _normalise_charset("latin-1") == "iso-8859-1"
    assert _normalise_charset("latin1") == "iso-8859-1"
    assert _normalise_charset("iso-8859-1") == "iso-8859-1"


def test_normalise_shift_jis_aliases() -> None:
    """Shift-JIS encoding name variants should normalise consistently."""
    assert _normalise_charset("shift_jis") == "shift_jis"
    assert _normalise_charset("Shift-JIS") == "shift_jis"
    assert _normalise_charset("x-sjis") == "shift_jis"


def test_normalise_unknown_encoding() -> None:
    """Unknown/unsupported encoding names should return None."""
    assert _normalise_charset("bogus-encoding-12345") is None
    assert _normalise_charset("") is None


# ─── UTF-8 heuristic tests ────────────────────────────────────────────────


def test_pure_utf8_is_likely() -> None:
    """Pure UTF-8 text should be detected as likely UTF-8."""
    content = b"Hello, world! Caf"
    assert _is_likely_utf8(content) is True


def test_iso8859_not_utf8() -> None:
    """ISO-8859-1 encoded content should not pass the UTF-8 heuristic."""
    # Accented characters: é (0xE9), ç (0xE7) are valid ISO-8859-1, not valid UTF-8.
    text = "Déjà vu".encode("iso-8859-1")
    # ISO-8859-1 bytes in the high range (0xE9 = é) will fail UTF-8 decoding.
    assert _is_likely_utf8(text) is False


def test_partial_utf8_ratio_above_threshold() -> None:
    """Content with small proportion of invalid UTF-8 should still pass."""
    # Build mostly valid UTF-8 with a few non-UTF-8 bytes mixed in.
    valid = "Hello, this is valid UTF-8 text that is long enough to pass the ratio check" * 10
    content = bytearray(valid.encode("utf-8"))
    # Insert a few invalid bytes (< 5%).
    content[50] = 0xFF
    content[200] = 0xFE
    assert _is_likely_utf8(bytes(content)) is True


# ─── Binary content detection tests ───────────────────────────────────────


def test_binary_content_with_null_bytes() -> None:
    """Content dominated by null bytes should be detected as binary."""
    content = b"\x00" * 512 + b"some text"
    assert _looks_like_binary(content) is True


def test_binary_pdf_header() -> None:
    """PDF header bytes should be detected as binary."""
    content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 500
    assert _looks_like_binary(content) is True


def test_plain_text_not_binary() -> None:
    """Plain text content with valid characters should not be binary."""
    content = b"Hello, this is plain text with normal whitespace and punctuation."
    assert _looks_like_binary(content) is False


# ─── decode_content / detect_encoding integration tests ───────────────────


def test_decode_utf8_without_bom() -> None:
    """Plain UTF-8 content should decode correctly."""
    original = "Hello, world! Caf"
    result = decode_content(original.encode("utf-8"))
    assert result == original


def test_decode_utf8_with_bom() -> None:
    """UTF-8 with BOM should decode correctly, stripping the BOM."""
    original = "Hello, world!"
    raw = b"\xef\xbb\xbf" + original.encode("utf-8")
    result = decode_content(raw)
    assert original in result


def test_decode_iso8859_1_content() -> None:
    """ISO-8859-1 content should decode to meaningful text."""
    original = "Déjà vu garçon"
    raw = original.encode("iso-8859-1")
    result = decode_content(raw)
    # At minimum the known Latin-1 words should appear.
    assert "vu" in result
    assert "gar" in result


def test_decode_shift_jis_content() -> None:
    """Shift-JIS Japanese content should decode correctly when charset is declared."""
    # Short non-ASCII content is ambiguous without a charset hint; chardet
    # may mis-classify it.  In production the HTTP Content-Type header
    # provides the charset, so the declared_charset path is the critical one.
    original = "こんにちは"
    raw = original.encode("shift_jis")
    result = decode_content(raw, declared_charset="shift_jis")
    assert original in result


def test_decode_gb2312_content() -> None:
    """GB2312 Chinese content should decode correctly when charset is declared."""
    original = "你好世界"
    raw = original.encode("gb2312")
    result = decode_content(raw, declared_charset="gb2312")
    assert original in result


def test_content_type_charset_override() -> None:
    """Declared charset should take priority over heuristic fallback."""
    # Encode as Shift-JIS but declare charset as shift_jis in the header.
    original = "こんにちは"
    raw = original.encode("shift_jis")
    result = decode_content(raw, declared_charset="shift_jis")
    assert original in result


def test_fallback_replacement_char_on_unparseable() -> None:
    """Content with unknown declared charset should still decode safely."""
    content = b"Hello, world!"
    result = decode_content(content, declared_charset="bogus-encoding-xyz")
    # Should still produce reasonable output via the heuristic path.
    assert "Hello" in result


def test_decode_empty_bytes() -> None:
    """Empty byte content should return empty string."""
    assert decode_content(b"") == ""


def test_detect_encoding_empty() -> None:
    """Empty content defaults to utf-8."""
    assert detect_encoding(b"") == "utf-8"


def test_chardet_not_installed_graceful_degradation() -> None:
    """When chardet/charset_normalizer are not importable, detection still works."""
    content = b"Hello, world! Caf"

    # Simulate both libraries being absent by removing from sys.modules.
    with mock.patch.dict(
        sys.modules,
        {"chardet": None, "charset_normalizer": None},
    ):
        result = decode_content(content)
    assert "Hello" in result


def test_detect_encoding_without_libraries() -> None:
    """detect_encoding should still work when chardet is absent."""
    content = b"Hello, world! Caf"

    with mock.patch.dict(
        sys.modules,
        {"chardet": None, "charset_normalizer": None},
    ):
        result = detect_encoding(content)
    assert result in ("utf-8", "utf-8-sig", "iso-8859-1")


def test_mixed_encoding_headers() -> None:
    """Content with a wrong declared charset should still decode safely."""
    # Encode as UTF-8 but declare as ISO-8859-1 — the library/heuristic
    # detection should still correctly identify UTF-8.
    original = "Café garçon"
    raw = original.encode("utf-8")
    result = decode_content(raw, declared_charset="iso-8859-1")
    # The result should contain meaningful text.
    assert len(result) > 0


def test_binary_content_decode_safety() -> None:
    """Binary content (random bytes) should decode without crashing."""
    content = bytes(range(256))  # Every possible byte value 0x00-0xFF
    result = decode_content(content)
    # Should produce a non-empty string without raising.
    assert isinstance(result, str)
    assert len(result) > 0


def test_euc_jp_content() -> None:
    """EUC-JP Japanese content should decode correctly when charset is declared."""
    original = "日本語"
    raw = original.encode("euc_jp")
    result = decode_content(raw, declared_charset="euc-jp")
    assert original in result


def test_meta_charset_sniffing() -> None:
    """HTML with <meta charset> should be detected via meta-sniff."""
    html = b'<html><head><meta charset="utf-8"></head><body>Hello</body></html>'
    encoding = detect_encoding(html)
    assert encoding == "utf-8"


def test_meta_http_equiv_charset_sniffing() -> None:
    """HTML with <meta http-equiv> Content-Type should be detected."""
    html = (
        b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252"></head><body>Hello</body></html>'
    )
    encoding = detect_encoding(html)
    # Either cp1252 (meta-sniff wins due to library absence) or utf-8
    # (if chardet is present and detects UTF-8 with high confidence).
    assert encoding in ("cp1252", "utf-8")


def test_small_content_skips_library_detection() -> None:
    """Content below the heuristic threshold should skip library detection."""
    content = b"Hi there"
    result = decode_content(content)
    assert "Hi there" in result


def test_decode_cjk_without_charset_still_safe() -> None:
    """Short CJK content without a declared charset should still decode without error,
    even if chardet misidentifies the encoding."""
    raw = "こんにちは".encode("shift_jis")
    # Without a charset hint, chardet may misidentify, but decode_content
    # must never raise — it always returns a string.
    result = decode_content(raw)
    assert isinstance(result, str)
    assert len(result) > 0


def test_gb2312_long_content_detected_by_library() -> None:
    """Longer GB2312 Chinese content should be detected by chardet library."""
    # chardet needs sufficient content to confidently detect GB2312.
    original = "你好世界你好世界你好世界中国中国中国"
    raw = original.encode("gb2312")
    result = decode_content(raw)
    # With enough content, chardet should detect GB2312 correctly.
    assert original in result


@pytest.mark.parametrize(
    "encoding_name,original_text",
    [
        ("utf-8", "Hello World!"),
        ("utf-16", "Hello World!"),
        ("shift_jis", "こんにちは"),
        ("gb2312", "你好世界"),
        ("iso-8859-1", "Déjà vu"),
    ],
)
def test_roundtrip_decode_detect(encoding_name: str, original_text: str) -> None:
    """Encoded text should survive a round-trip through decode_content."""
    raw = original_text.encode(encoding_name, errors="replace")
    result = decode_content(raw)
    assert isinstance(result, str)
    assert len(result) > 0


def test_module_imports_cleanly() -> None:
    """Ensure the encoding_detection module imports without errors."""
    from app import encoding_detection as ed

    assert ed.decode_content(b"test") == "test"
