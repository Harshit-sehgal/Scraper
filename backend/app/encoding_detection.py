"""Encoding detection and robust byte-to-string decoding (Roadmap Rel 11).

Provides two public helpers:

* ``detect_encoding(content, declared_charset)`` — best-effort encoding name.
* ``decode_content(content, declared_charset)`` — decode *bytes* to *str*
  using the detected (or declared) encoding, with ``errors="replace"`` as a
  safety net so callers never crash on bad byte sequences.

Detection cascade (first confident result wins):
1. BOM (byte-order mark) sniffing — UTF-8/16/32 variants.
2. ``charset_normalizer`` if installed (fast, pure-Python).
3. ``chardet`` if installed (classic, slower).
4. HTTP ``Content-Type`` charset (``declared_charset`` parameter).
5. ``<meta charset=…>`` / ``<meta http-equiv="Content-Type"…>`` sniffing.
6. UTF-8 heuristic (valid-UTF-8 ratio check).
7. Fallback to ``iso-8859-1`` (Latin-1, never fails per spec).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ─── BOM definitions ─────────────────────────────────────────────────────
# Map byte-order-mark byte sequences to their canonical codec names.
# Order matters: longer BOMs must be checked before shorter prefixes that
# share the same opening bytes (e.g. UTF-32 before UTF-16).
_BOM_TABLE: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]

# Minimum content length below which heuristic detection is unreliable.
_MIN_HEURISTIC_LENGTH = 32

# Ratio of valid UTF-8 bytes above which we treat content as UTF-8.
_UTF8_VALID_RATIO_THRESHOLD = 0.95

# Confidence threshold from chardet/charset_normalizer below which we ignore
# the library result and continue down the cascade.
_CONFIDENCE_THRESHOLD = 0.7

# Common alias normalisation — map alternate names to canonical Python codec names.
_CHARSET_ALIASES: dict[str, str] = {
    "ascii": "utf-8",  # ASCII is a subset of UTF-8; decode as UTF-8.
    "iso-8859-1": "iso-8859-1",
    "latin-1": "iso-8859-1",
    "latin1": "iso-8859-1",
    "iso-8859-2": "iso-8859-2",
    "iso-8859-5": "iso-8859-5",
    "iso-8859-15": "iso-8859-15",
    "windows-1252": "cp1252",
    "win-1252": "cp1252",
    "cp1252": "cp1252",
    "shift_jis": "shift_jis",
    "shift-jis": "shift_jis",
    "sjis": "shift_jis",
    "x-sjis": "shift_jis",
    "euc-jp": "euc_jp",
    "euc_kr": "euc_kr",
    "euc-kr": "euc_kr",
    "gb2312": "gb2312",
    "gbk": "gbk",
    "gb18030": "gb18030",
    "big5": "big5",
    "csbig5": "big5",
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "utf-8-sig": "utf-8-sig",
    "utf-16": "utf-16",
    "utf-16le": "utf-16-le",
    "utf-16be": "utf-16-be",
    "utf-32": "utf-32",
    "utf-32le": "utf-32-le",
    "utf-32be": "utf-32-be",
}


# ─── Internal helpers ──────────────────────────────────────────────────────


def _normalise_charset(raw: str) -> str | None:
    """Return a canonical codec name for *raw*, or ``None`` if unknown."""
    key = raw.strip().lower().replace(" ", "-")
    return _CHARSET_ALIASES.get(key)


def _detect_bom(content: bytes) -> str | None:
    """Return the codec name implied by a BOM prefix, or ``None``."""
    for bom_bytes, codec in _BOM_TABLE:
        if content.startswith(bom_bytes):
            return codec
    return None


def _detect_via_library(content: bytes) -> str | None:
    """Try charset_normalizer / chardet; return encoding name or ``None``."""
    # 1. charset_normalizer (preferred — fast, pure-Python)
    try:
        import charset_normalizer  # type: ignore[import-untyped]

        results = charset_normalizer.from_bytes(content)
        best = results.best()
        if best is not None:
            encoding_name = best.encoding
            if encoding_name is not None:
                normalised = _normalise_charset(encoding_name)
                if normalised is not None:
                    return normalised
    except (ImportError, ModuleNotFoundError):
        pass
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.debug("charset_normalizer detection failed: %s", exc)

    # 2. chardet
    try:
        import chardet  # type: ignore[import-untyped]

        result = chardet.detect(content)
        if result and (encoding := result.get("encoding")):
            confidence = result.get("confidence", 0.0)
            if confidence >= _CONFIDENCE_THRESHOLD:
                normalised = _normalise_charset(encoding)
                if normalised is not None:
                    return normalised
    except (ImportError, ModuleNotFoundError):
        pass
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.debug("chardet detection failed: %s", exc)

    return None


def _sniff_meta_charset(content: bytes) -> str | None:
    """Sniff ``<meta charset>`` / ``<meta http-equiv=Content-Type>`` from raw bytes.

    Reads only the first 4 KiB to avoid scanning entire payloads.
    """
    head = content[:4096]
    try:
        head_text = head.decode("ascii", errors="replace")
    except (UnicodeDecodeError, ValueError):
        return None

    # <meta charset="utf-8">
    match = re.search(r'<\s*meta[^>]+charset\s*=\s*["\']?\s*([^"\';\s>]+)', head_text, re.IGNORECASE)
    if match:
        return _normalise_charset(match.group(1))

    # <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    match = re.search(
        r'<\s*meta[^>]+http-equiv\s*=\s*["\']?Content-Type["\']?[^>]+content\s*=\s*["\'][^"\']*charset=([^"\';\s>]+)',
        head_text,
        re.IGNORECASE,
    )
    if match:
        return _normalise_charset(match.group(1))

    return None


def _is_likely_utf8(content: bytes) -> bool:
    """Heuristic: return ``True`` if *content* looks like valid UTF-8 text.

    We try a full UTF-8 decode; if it succeeds, it's UTF-8.  For partial
    validity (mixed encodings mixed in), we check the ratio of bytes that
    successfully decode.
    """
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass

    # Partial decode: count how many replacement characters we'd get.
    decoded = content.decode("utf-8", errors="replace")
    replacement_count = decoded.count("�")
    if len(decoded) == 0:
        return False
    valid_ratio = 1.0 - (replacement_count / len(decoded))
    return valid_ratio >= _UTF8_VALID_RATIO_THRESHOLD


def _looks_like_binary(content: bytes) -> bool:
    """Rough heuristic: return ``True`` if the content appears to be binary (not text).

    Checks the first 1 KiB for a high proportion of null bytes or control
    characters that would not appear in typical text.
    """
    sample = content[:1024]
    if not sample:
        return False
    null_count = sample.count(0)
    # If more than 30 % null bytes, almost certainly binary.
    if len(sample) > 0 and (null_count / len(sample)) > 0.30:
        return True
    # Count C0 control characters (0x00-0x1F) excluding \t, \n, \r.
    control_count = sum(1 for b in sample if b < 0x20 and b not in (0x09, 0x0A, 0x0D))
    return len(sample) > 0 and (control_count / len(sample)) > 0.30


def _looks_like_gb2312(content: bytes) -> bool:
    """Recognise common GB2312 byte pairs when optional detectors are absent."""
    pairs = 0
    valid_pairs = 0
    index = 0
    while index + 1 < len(content):
        first, second = content[index], content[index + 1]
        if first >= 0x80:
            pairs += 1
            if 0xA1 <= first <= 0xF7 and 0xA1 <= second <= 0xFE:
                valid_pairs += 1
            index += 2
        else:
            index += 1
    return pairs >= 2 and valid_pairs / pairs >= 0.75


# ─── Public API ────────────────────────────────────────────────────────────


def detect_encoding(content: bytes, declared_charset: str | None = None) -> str:
    """Detect the most likely character encoding of *content*.

    Parameters
    ----------
    content:
        Raw byte payload.
    declared_charset:
        Charset from the HTTP ``Content-Type`` header or equivalent
        out-of-band signal. Used as a lower-priority hint after library
        detection but before heuristic fallbacks.

    Returns
    -------
    str
        A canonical Python codec name (always a non-empty string).
    """
    if not content:
        return "utf-8"

    # 1. BOM detection — highest confidence.
    bom_codec = _detect_bom(content)
    if bom_codec is not None:
        return bom_codec

    # 2. Library-based detection (charset_normalizer or chardet).
    if len(content) >= _MIN_HEURISTIC_LENGTH:
        lib_codec = _detect_via_library(content)
        if lib_codec is not None:
            return lib_codec

    # 3. Declared charset (e.g. HTTP Content-Type header).
    if declared_charset:
        normalised = _normalise_charset(declared_charset)
        if normalised is not None:
            return normalised

    # 4. <meta charset> sniffing from the raw bytes.
    meta_codec = _sniff_meta_charset(content)
    if meta_codec is not None:
        return meta_codec

    # 5. Common CJK legacy encoding heuristic. This keeps pages readable in
    # minimal deployments where optional charset detectors are not installed.
    if _looks_like_gb2312(content):
        return "gb2312"

    # 6. UTF-8 heuristic.
    if _is_likely_utf8(content):
        return "utf-8"

    # 7. Final fallback: iso-8859-1 (Latin-1) — never fails, every byte is valid.
    return "iso-8859-1"


def decode_content(content: bytes, declared_charset: str | None = None) -> str:
    """Decode *content* bytes to a string using detected or declared encoding.

    Sequence:
    1. Detect encoding via :func:`detect_encoding`.
    2. Try to decode with that encoding.
    3. If that fails, try UTF-8 with ``errors="replace"``.
    4. If *that* fails (shouldn't, but defensive), fall back to
       ``iso-8859-1`` with ``errors="replace"``.

    The function never raises ``UnicodeDecodeError``.
    """
    if not content:
        return ""

    encoding = detect_encoding(content, declared_charset=declared_charset)

    # Try the detected encoding.
    try:
        return content.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError, ValueError) as exc:
        logger.debug("decode with %s failed (%s); falling back to utf-8", encoding, exc)

    # Fallback 1: UTF-8 with replacement.
    try:
        return content.decode("utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError, ValueError) as exc:
        logger.debug("utf-8 fallback failed (%s); falling back to iso-8859-1", exc)

    # Fallback 2: iso-8859-1 (never fails).
    return content.decode("iso-8859-1", errors="replace")
