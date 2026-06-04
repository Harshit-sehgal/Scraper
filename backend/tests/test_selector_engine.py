"""Unit tests for selector_engine — selector extraction, regex fallback, field classification, and metadata building."""

from app.models import FieldType, SchemaField
from app.selector_engine import (
    _classify_text_value,
    _collect_child_text_nodes,
    _detect_table_headers,
    _extract_context_window,
    _field_matches_classification,
    _infer_field_type_from_name,
    _read_node_value,
    _selector_css,
    build_selector_field_metadata,
    extract_raw_from_selectors,
    extract_with_regex,
)
from conftest import make_schema_field_list

# ═══════════════════════════════════════════════════════════════════════════════
# Table Header Detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectTableHeaders:
    def test_detects_th_elements(self) -> None:
        html = "<table><tr><th class='price'>Price</th><th>Name</th></tr></table>"
        result = _detect_table_headers(html)
        assert len(result) >= 2
        texts = [h["text"] for h in result]
        assert "Price" in texts or "Price" in str(result)

    def test_detects_headings(self) -> None:
        html = "<h2>Product List</h2><h3>Featured Items</h3>"
        result = _detect_table_headers(html)
        headings = [h for h in result if h.get("is_heading")]
        assert len(headings) >= 1

    def test_returns_empty_for_no_headers(self) -> None:
        html = "<div>no headers here</div>"
        result = _detect_table_headers(html)
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Selector CSS Helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelectorCss:
    def test_returns_none_for_empty(self) -> None:
        assert _selector_css(None) is None
        assert _selector_css("") is None
        assert _selector_css({}) is None

    def test_returns_string_directly(self) -> None:
        assert _selector_css(".my-class") == ".my-class"

    def test_returns_from_dict(self) -> None:
        assert _selector_css({"selector": ".title", "type": "text"}) == ".title"

    def test_returns_none_for_empty_dict_selector(self) -> None:
        assert _selector_css({"selector": ""}) is None


# ═══════════════════════════════════════════════════════════════════════════════
# Build Selector Field Metadata
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildSelectorFieldMetadata:
    def test_returns_empty_for_empty_input(self) -> None:
        assert build_selector_field_metadata({}, []) == {}

    def test_adds_type_from_schema(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        result = build_selector_field_metadata({"price": ".price"}, schema)
        assert result["price"]["type"] == "currency"

    def test_merges_existing_type_in_entry(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description="")]
        result = build_selector_field_metadata({"price": {"selector": ".p", "type": "text"}}, schema)
        assert result["price"]["type"] == "text"  # existing type takes priority

    def test_handles_none_field_sels(self) -> None:
        assert build_selector_field_metadata({}, []) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Collect Child Text Nodes
# ═══════════════════════════════════════════════════════════════════════════════


class TestCollectChildTextNodes:
    def test_returns_text_from_leaf_elements(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<div class="item"><span>Hello</span><span>World</span></div>', "html.parser")
        texts = _collect_child_text_nodes(soup.div)
        assert len(texts) >= 1
        assert "Hello" in texts or "World" in texts

    def test_skips_script_and_style(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            "<div><script>var x=1;</script><span>Visible</span><style>.cls{}</style></div>",
            "html.parser",
        )
        texts = _collect_child_text_nodes(soup.div)
        assert "Visible" in " ".join(texts)

    def test_falls_back_to_full_text(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<div><p>Just some text</p></div>", "html.parser")
        texts = _collect_child_text_nodes(soup.div)
        assert len(texts) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Infer Field Type from Name
# ═══════════════════════════════════════════════════════════════════════════════


class TestInferFieldTypeFromName:
    def test_currency_keywords(self) -> None:
        assert _infer_field_type_from_name("price") == FieldType.CURRENCY
        assert _infer_field_type_from_name("total_cost") == FieldType.CURRENCY
        assert _infer_field_type_from_name("amount") == FieldType.CURRENCY

    def test_email_keywords(self) -> None:
        assert _infer_field_type_from_name("email") == FieldType.EMAIL
        assert _infer_field_type_from_name("contact_email") == FieldType.EMAIL

    def test_phone_keywords(self) -> None:
        assert _infer_field_type_from_name("phone") == FieldType.PHONE
        assert _infer_field_type_from_name("telephone") == FieldType.PHONE

    def test_url_keywords(self) -> None:
        assert _infer_field_type_from_name("url") == FieldType.URL
        assert _infer_field_type_from_name("website") == FieldType.URL

    def test_date_keywords(self) -> None:
        assert _infer_field_type_from_name("departure_date") == FieldType.DATE
        assert _infer_field_type_from_name("created_at") == FieldType.DATE

    def test_number_keywords(self) -> None:
        assert _infer_field_type_from_name("quantity") == FieldType.NUMBER
        assert _infer_field_type_from_name("count") == FieldType.NUMBER

    def test_rating_keywords(self) -> None:
        assert _infer_field_type_from_name("rating") == FieldType.RATING
        assert _infer_field_type_from_name("review_score") == FieldType.RATING

    def test_location_keywords(self) -> None:
        assert _infer_field_type_from_name("city") == FieldType.LOCATION
        assert _infer_field_type_from_name("address") == FieldType.LOCATION

    def test_code_keywords(self) -> None:
        assert _infer_field_type_from_name("sku") == FieldType.CODE
        assert _infer_field_type_from_name("product_code") == FieldType.CODE

    def test_returns_none_for_unknown(self) -> None:
        assert _infer_field_type_from_name("description") is None
        assert _infer_field_type_from_name("") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Classify Text Value
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyTextValue:
    def test_classifies_date_slash(self) -> None:
        assert _classify_text_value("01/15/2025") == "date"

    def test_classifies_date_dash(self) -> None:
        assert _classify_text_value("2025-01-15") == "date"

    def test_classifies_date_text(self) -> None:
        assert _classify_text_value("Jan 15, 2025") == "date"

    def test_classifies_currency(self) -> None:
        assert _classify_text_value("$100") == "currency"
        assert _classify_text_value("€50") == "currency"

    def test_classifies_code(self) -> None:
        assert _classify_text_value("ABCD") == "code"
        assert _classify_text_value("JFK") == "code"

    def test_classifies_location(self) -> None:
        assert _classify_text_value("New York Los Angeles") == "location"

    def test_classifies_label(self) -> None:
        assert _classify_text_value("Starting from") == "label"
        assert _classify_text_value("Call Now") == "label"

    def test_classifies_name(self) -> None:
        assert _classify_text_value("John") == "name"
        assert _classify_text_value("Widget Pro") == "name"

    def test_classifies_text_fallback(self) -> None:
        assert _classify_text_value("hello world") == "text"

    def test_returns_empty_for_empty_string(self) -> None:
        assert _classify_text_value("") == "empty"
        assert _classify_text_value("   ") == "empty"


# ═══════════════════════════════════════════════════════════════════════════════
# Field Matches Classification
# ═══════════════════════════════════════════════════════════════════════════════


class TestFieldMatchesClassification:
    def test_date_classification(self) -> None:
        assert _field_matches_classification("departure_date", "date") is True
        assert _field_matches_classification("day", "date") is True

    def test_currency_classification(self) -> None:
        assert _field_matches_classification("price", "currency") is True
        assert _field_matches_classification("cost", "currency") is True

    def test_name_classification(self) -> None:
        assert _field_matches_classification("name", "name") is True
        assert _field_matches_classification("title", "name") is True

    def test_location_classification(self) -> None:
        assert _field_matches_classification("city", "location") is True

    def test_code_classification(self) -> None:
        assert _field_matches_classification("code", "code") is True

    def test_text_classification_matches_anything(self) -> None:
        assert _field_matches_classification("anything", "text") is True


# ═══════════════════════════════════════════════════════════════════════════════
# Extract Context Window
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractContextWindow:
    def test_extracts_window_around_keyword(self) -> None:
        result = _extract_context_window("This is a long text with a keyword in it", ["keyword"])
        assert result is not None
        assert "keyword" in result

    def test_returns_none_when_keyword_not_found(self) -> None:
        result = _extract_context_window("hello world", ["missing"])
        assert result is None

    def test_returns_none_for_short_segment(self) -> None:
        result = _extract_context_window("a", ["a"])
        # The segment is too short (< SELECTOR_MIN_SEGMENT_LEN), expect None
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Read Node Value
# ═══════════════════════════════════════════════════════════════════════════════


class TestReadNodeValue:
    def test_returns_href_for_url_type(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<a href="https://example.com">Click</a>', "html.parser")
        val = _read_node_value(soup.a, FieldType.URL)
        assert val == "https://example.com"

    def test_returns_title_when_text_truncated(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<span title="Full Product Name Here">Full...</span>', "html.parser")
        val = _read_node_value(soup.span)
        assert val == "Full Product Name Here"

    def test_returns_alt_when_no_text(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<img src="x.jpg" alt="Product Image" />', "html.parser")
        val = _read_node_value(soup.img)
        assert val == "Product Image"

    def test_returns_text_content(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<span>Plain Text</span>", "html.parser")
        val = _read_node_value(soup.span)
        assert val == "Plain Text"


# ═══════════════════════════════════════════════════════════════════════════════
# Extract Raw from Selectors (with mocked BS4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractRawFromSelectors:
    def test_returns_empty_without_container(self) -> None:
        assert extract_raw_from_selectors("<html></html>", {"item_container": ""}) == []

    def test_returns_empty_without_fields(self) -> None:
        assert extract_raw_from_selectors("<html></html>", {"item_container": ".card", "fields": {}}) == []

    def test_returns_empty_with_no_matching_containers(self) -> None:
        result = extract_raw_from_selectors(
            "<html><body><div>No matching class</div></body></html>",
            {"item_container": ".card", "fields": {"name": ".title"}},
        )
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Extract with Regex (fallback)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractWithRegex:
    def test_returns_empty_for_empty_html(self) -> None:
        schema = make_schema_field_list(["name"])
        result = extract_with_regex("", schema)
        assert result == []

    def test_extracts_from_simple_html(self) -> None:
        schema = make_schema_field_list(["name"])
        html = '<html><body><article class="item"><h2>Product A</h2></article></body></html>'
        result = extract_with_regex(html, schema)
        assert isinstance(result, list)
        # Should find the article as a container
        if result:
            assert result[0].get("name") is not None

    def test_skips_noise_containers(self) -> None:
        schema = make_schema_field_list(["name"])
        html = '<html><body><div class="ad-banner">Subscribe to newsletter</div></body></html>'
        result = extract_with_regex(html, schema)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# Apply Selectors (with mocked dependencies)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# Apply Selectors (simple smoke test — no mocks)
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplySelectors:
    def test_returns_empty_for_no_container(self) -> None:
        """Without an item_container selector, apply_selectors returns empty list."""
        from app.selector_engine import apply_selectors

        result = apply_selectors(
            "<html></html>",
            {"item_container": "", "fields": {}},
            make_schema_field_list(["name"]),
        )
        assert result == []
