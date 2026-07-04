"""Unit Tests for app.page_profiler.

page_profiler.py had ZERO test coverage — every existing test in the suite
mocks ``detect_page_structure`` / ``detect_value_patterns`` with canned
return values, so the real regex and structure-dispatch logic never
executed under test. These tests exercise the public API with real HTML
fixtures (no mocking required — the module is pure bs4 + stdlib ``re``).

High-value targets covered:
  * All 18 VALUE_PATTERNS regex groups (table-driven) — url_value_classification.py:58
    depends on these regexes matching real-world value text.
  * code_3letter COMMON_3LETTER_WORDS exclusion contract (THE/AND/FOR filtered,
    LON/PAR/BOM retained) — the only group with bespoke post-filtering logic.
  * detect_page_structure dispatch + confidence thresholds across all 5 structure
    types (table / cards / list / key_value-dl / key_value-2col-table / mixed).
  * dedup + cap-at-10 contract, get_text-only operation (no tag leakage),
    noise-tag stripping, container-selector shape.
"""

from __future__ import annotations

import pytest
from app.page_profiler import (
    VALUE_PATTERNS,
    StructureProfile,
    ValuePatterns,
    detect_page_structure,
    detect_value_patterns,
)

# ── Dataclass smoke tests ─────────────────────────────────────────────


class TestDataclassDefaults:
    def test_structure_profile_defaults(self) -> None:
        profile = StructureProfile(structure_type="mixed", container_selector="body")
        assert profile.structure_type == "mixed"
        assert profile.container_selector == "body"
        assert profile.headers == []
        assert profile.structure_confidence == 0.0
        assert profile.sample_containers == []

    def test_value_patterns_defaults_all_empty_lists(self) -> None:
        patterns = ValuePatterns()
        # Every field must default to an independent empty list.
        for field_name in (
            "currencies",
            "dates",
            "ratings",
            "codes_3letter",
            "phones",
            "emails",
            "numbers",
            "durations",
            "urls",
            "weights",
            "percentages",
            "times",
            "booleans",
            "dimensions",
            "quantities",
            "product_codes",
            "units",
            "address_fragments",
        ):
            assert getattr(patterns, field_name) == []

    def test_value_patterns_field_independence(self) -> None:
        """Default factory must produce distinct list instances per field."""
        patterns = ValuePatterns()
        patterns.currencies.append("$")
        # Mutating one field must not bleed into another.
        assert patterns.dates == []
        assert patterns.numbers == []


# ── VALUE_PATTERNS regex table-driven coverage (highest value) ───────
#
# Every regex group gets a minimal HTML fixture containing exactly one
# value of the kind that pattern is meant to detect. This catches any
# regex regression that url_value_classification.py / selector_discovery
# depend on.

VALUE_FIXTURES = [
    # (pattern_type, html_snippet, expected_match_substring)
    # NOTE: re.findall with capturing groups returns only group content,
    # not the full match. E.g. r"\d+[\d,]*\s*(inr|usd|...)" captures
    # just "USD" from "5000 USD", not "5000 USD".
    ("currency", "Price: $450.00 today", "$450.00"),
    ("currency", "Cost: 5000 INR only", "INR"),
    ("currency", "Rs. 500 flat", "Rs."),
    ("currency", "Budget: 1.2Cr deal", "Cr"),
    ("date", "Updated 22-05-2026", "22-05-2026"),
    ("date", "Published 2026-05-22", "2026"),
    ("date", "May 22 release", "May"),
    ("date", "22 May release", "May"),
    ("rating", "Scored <span>8.5/10</span> great", "8.5/10"),
    ("rating", "<span>★★★</span> excellent", "★"),
    ("rating", "4.5 stars rated", "star"),
    ("rating", "<span>[4/5]</span> rating", "4/5"),
    ("code_3letter", "LON to PAR flight", "LON"),
    ("duration", "Runtime 2h 30m", "2h"),
    ("duration", "Took 3 hours", "hours"),
    ("phone", "Call +91 9876543210", "+91 9876543210"),
    ("email", "Mail user@example.com please", "user@example.com"),
    ("number", "Sold 1,234.56 units", "1,234.56"),
    ("url", "Visit <span>https://example.com/path</span>", "https://example.com/path"),
    ("url", "See <span>www.example.org</span> here", "www.example.org"),
    ("weight", "Weight 250g net", "250g"),
    ("weight", "Weight 1 kg gross", "kg"),
    ("percentage", "Discount 8% today", "8%"),
    ("percentage", "0.5% margin", "0.5%"),
    ("time", "Opens 14:30 sharp", "14:30"),
    ("time", "Closes 2:30 PM", "PM"),
    ("boolean", "Status: In Stock", "In Stock"),
    ("boolean", "Flag Yes", "Yes"),
    ("dimension", "Size 10x15cm", "10x15cm"),
    ("quantity", "Pack of 6 units", "Pack of 6"),
    ("quantity", "500ml bottle", "500ml"),
    ("product_code", "SKU-12345 item", "SKU-12345"),
    ("product_code", "EAN 1234567890123 code", "EAN 1234567890123"),
    ("unit_type", "priced per kg", "per kg"),
    ("unit_type", "sold each", "each"),
    ("address", "Office 123 Main St", "123 Main St"),
]


@pytest.mark.parametrize(
    "pattern_type, html, expected_substring",
    VALUE_FIXTURES,
    ids=[f"{p}-{i}" for i, (p, _, _) in enumerate(VALUE_FIXTURES)],
)
def test_value_patterns_regex_matches(
    pattern_type: str,
    html: str,
    expected_substring: str,
) -> None:
    """Each VALUE_PATTERNS regex group must find its target value type."""
    patterns = detect_value_patterns(html)
    # pattern_type -> ValuePatterns attribute (mirrors the module's pattern_map).
    attr_map = {
        "currency": "currencies",
        "date": "dates",
        "rating": "ratings",
        "code_3letter": "codes_3letter",
        "phone": "phones",
        "email": "emails",
        "number": "numbers",
        "duration": "durations",
        "url": "urls",
        "weight": "weights",
        "percentage": "percentages",
        "time": "times",
        "boolean": "booleans",
        "dimension": "dimensions",
        "quantity": "quantities",
        "product_code": "product_codes",
        "unit_type": "units",
        "address": "address_fragments",
    }
    field = getattr(patterns, attr_map[pattern_type])
    joined = " ".join(field)
    assert expected_substring.lower() in joined.lower(), (
        f"pattern_type={pattern_type!r}: expected {expected_substring!r} in {field!r}"
    )


def test_value_patterns_dedup() -> None:
    r"""Repeated values collapse to a single entry (set-based dedup).

    The currency regex ``r"\d+[\d,]*\s*(inr|usd|eur|gbp|aud|cad)"``
    captures only the currency-code group, so "USD 100" → "USD".
    Three identical "USD 100" lines produce three "USD" captures,
    deduped to one entry.
    """
    html = "$100 \n $100 \n $100"
    patterns = detect_value_patterns(html)
    # Three "$100" matches via the symbol-based currency regex
    # (r"[\$₨€£¥₹]\s*\d+...") dedup to one.
    currency_str = " ".join(patterns.currencies)
    assert currency_str.count("$100") == 1


def test_value_patterns_cap_at_10() -> None:
    """No value-pattern field may exceed 10 entries (the module's cap)."""
    # 15 distinct integers — every one matches the "number" generic regex.
    html = " ".join(str(n) for n in range(11, 26))  # 11..25 → 15 numbers
    patterns = detect_value_patterns(html)
    assert len(patterns.numbers) <= 10, f"numbers exceeded cap-at-10: {patterns.numbers!r}"


def test_code_3letter_excludes_common_words() -> None:
    """Common 3-letter English words (THE/AND/FOR) are filtered out,
    real airport/stock codes (LON/PAR) are retained."""
    html = "THE AND FOR ARE NOT YOU ALL LON PAR BOM DEL"
    patterns = detect_value_patterns(html)
    upper = {c.upper() for c in patterns.codes_3letter}
    assert "LON" in upper
    assert "PAR" in upper
    assert "BOM" in upper
    assert "THE" not in upper
    assert "AND" not in upper
    assert "FOR" not in upper


def test_value_patterns_uses_text_not_tags() -> None:
    """detect_value_patterns operates on get_text(); tag/attribute strings
    must not leak into results."""
    html = "<div class='card' data-sku='SKU-XYZ'>Just text here</div>"
    patterns = detect_value_patterns(html)
    # The deliberate attribute value SKU-XYZ must not surface as a product_code.
    product_str = " ".join(patterns.product_codes)
    assert "SKU-XYZ" not in product_str


def test_value_patterns_empty_html() -> None:
    """Empty / whitespace-only HTML produces an all-empty ValuePatterns."""
    patterns = detect_value_patterns("")
    assert patterns == ValuePatterns()
    patterns_ws = detect_value_patterns("   \n\t  ")
    assert patterns_ws == ValuePatterns()


def test_value_patterns_exposed_dict_has_18_groups() -> None:
    """The module-level VALUE_PATTERNS contract: exactly 18 regex groups.
    url_value_classification.py reads this dict directly."""
    assert len(VALUE_PATTERNS) == 18


# ── detect_page_structure dispatch + confidence thresholds ────────────


def test_detect_table_structure() -> None:
    """A real data table (<th> headers + >2 rows) yields structure_type='table'
    with confidence strictly above the 0.8 dispatch threshold."""
    html = """
    <table>
      <tr><th>Name</th><th>Price</th><th>Stock</th></tr>
      <tr><td>Widget</td><td>$10</td><td>Yes</td></tr>
      <tr><td>Gadget</td><td>$20</td><td>No</td></tr>
      <tr><td>Doohickey</td><td>$30</td><td>Yes</td></tr>
    </table>
    """
    profile = detect_page_structure(html)
    assert profile.structure_type == "table"
    assert profile.structure_confidence > 0.8
    assert profile.container_selector == "table tr"
    assert profile.headers == ["Name", "Price", "Stock"]


def test_detect_cards_structure() -> None:
    """A grid of card divs (class~'card' / 'product') yields structure_type='cards'
    with confidence above the 0.7 dispatch threshold."""
    html = """
    <div>
      <div class="product-card">Widget A costs ten dollars and has a long description here</div>
      <div class="product-card">Widget B costs twenty dollars and has a long description here</div>
      <div class="product-card">Widget C costs thirty dollars and has a long description here</div>
      <div class="product-card">Widget D costs forty dollars and has a long description here</div>
    </div>
    """
    profile = detect_page_structure(html)
    assert profile.structure_type == "cards"
    assert profile.structure_confidence > 0.7


def test_detect_list_structure() -> None:
    """A <ul> with ≥12 <li> children yields structure_type='list' above 0.7.
    Confidence formula: min(0.5 + max_items/50, 0.8).  With 12 items:
    0.5 + 12/50 = 0.74 > 0.7 dispatch threshold."""
    items = "".join(f"<li>Item number {i} description text here</li>" for i in range(12))
    html = f"<ul>{items}</ul>"
    profile = detect_page_structure(html)
    assert profile.structure_type == "list"
    assert profile.structure_confidence > 0.7
    assert profile.container_selector == "ul li"


def test_detect_key_value_dl_structure() -> None:
    """A definition list (<dl> with >3 <dt>) yields structure_type='key_value'."""
    html = """
    <dl>
      <dt>Name</dt><dd>Widget</dd>
      <dt>Price</dt><dd>$10</dd>
      <dt>Stock</dt><dd>Yes</dd>
      <dt>SKU</dt><dd>ABC123</dd>
    </dl>
    """
    profile = detect_page_structure(html)
    assert profile.structure_type == "key_value"
    assert profile.container_selector == "dl"
    assert profile.headers[:4] == ["Name", "Price", "Stock", "SKU"]


def test_detect_key_value_two_column_table() -> None:
    """A 2-column table with ≥5 rows passes the key_value 2-column branch.

    The module hardcodes confidence=0.6 for the 2-column path, and the
    dispatch requires ``> 0.6`` (strict).  With exactly 3 rows, confidence
    is 0.6 which fails the strict check, so the structure falls through to
    'mixed'.  With 5+ rows, the helper's internal row-count check passes
    but the dispatch threshold still applies. This test verifies the
    *actual* behaviour of the public function for a moderate-size 2-col
    table — the current dispatch threshold rejects exactly-0.6 confidence,
    so the result is 'mixed'.
    """
    html = """
    <table>
      <tr><td>Name</td><td>Widget</td></tr>
      <tr><td>Price</td><td>$10</td></tr>
      <tr><td>Stock</td><td>Yes</td></tr>
      <tr><td>Color</td><td>Blue</td></tr>
      <tr><td>Size</td><td>Large</td></tr>
    </table>
    """
    profile = detect_page_structure(html)
    # Confidence is exactly 0.6; dispatch requires STRICT > 0.6.
    # The helper finds the structure, but the public function rejects it.
    # This documents the current behaviour — if the threshold is ever
    # relaxed to >= 0.6 this test will catch the behavioural change.
    assert profile.structure_type == "mixed"


def test_detect_mixed_fallback_on_empty() -> None:
    """Bare text with no recognizable structure falls back to 'mixed'."""
    html = "<p>Just some prose with no table, cards, list, or key-value markup.</p>"
    profile = detect_page_structure(html)
    assert profile.structure_type == "mixed"
    assert profile.structure_confidence == pytest.approx(0.3)
    assert profile.container_selector == "body"


def test_detect_structure_strips_noise_tags() -> None:
    """<script> / <style> / <nav> / <footer> / <header> are decomposed first
    and must not influence structure detection."""
    html = """
    <html>
      <header><nav>nav link nav link nav link nav link nav link</nav></header>
      <script>var x = 'card card card card card card card';</script>
      <style>.product-card { color: red; }</style>
      <footer><ul><li>legal</li><li>terms</li></ul></footer>
    </html>
    """
    profile = detect_page_structure(html)
    # No real cards/list survive noise stripping → mixed fallback.
    assert profile.structure_type == "mixed"


def test_table_beats_cards_precedence() -> None:
    """When a substantial data table is present it wins over cards.

    The table is checked first (0.8 threshold), so a table with strong
    signal (2+ headers, 15+ rows → confidence ≈ 0.85) beats even
    high-confidence card divs (~0.82).
    """
    # 15 data rows to push table confidence above 0.8 AND above cards' ~0.82.
    rows = "".join(f"<tr><td>Item {i}</td><td>${i * 10}</td></tr>" for i in range(15))
    html = f"""
    <div>
      <div class="card">card one card one card one card one card one card one</div>
      <div class="card">card two card two card two card two card two card two</div>
      <div class="card">card three card three card three card three card three</div>
      <table>
        <tr><th>Product</th><th>Price</th></tr>
        {rows}
      </table>
    </div>
    """
    profile = detect_page_structure(html)
    assert profile.structure_type == "table"
    assert profile.structure_confidence > 0.8


def test_detect_page_structure_empty_html() -> None:
    """Empty HTML still returns a valid (mixed) profile, never raises."""
    profile = detect_page_structure("")
    assert profile.structure_type == "mixed"
    assert isinstance(profile, StructureProfile)
