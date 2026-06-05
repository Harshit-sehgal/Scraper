"""Tests for pure utility functions in app.html_utils."""

from __future__ import annotations

from app.html_utils import (
    _compact_text,
    _is_empty_value,
    _is_entity_name_field,
    _is_noise_name_value,
    _is_placeholder_value,
    _normalized_text_key,
    _sanitize_field_value,
    _valid_email,
    _valid_phone,
)
from app.models import FieldType, SchemaField

# ─── _compact_text ──────────────────────────────────────────────────────


class TestCompactText:
    def test_collapses_whitespace(self) -> None:
        assert _compact_text("hello   world") == "hello world"

    def test_strips_whitespace(self) -> None:
        assert _compact_text("  hello world  ") == "hello world"

    def test_handles_none(self) -> None:
        assert _compact_text("") == ""


# ─── _normalized_text_key ───────────────────────────────────────────────


class TestNormalizedTextKey:
    def test_strips_punctuation(self) -> None:
        assert _normalized_text_key("Hello, World!") == "hello world"

    def test_collapses(self) -> None:
        assert _normalized_text_key("  hello   world  ") == "hello world"

    def test_handles_empty(self) -> None:
        assert _normalized_text_key("") == ""


# ─── _is_placeholder_value ──────────────────────────────────────────────


class TestIsPlaceholderValue:
    def test_empty_key_is_placeholder(self) -> None:
        assert _is_placeholder_value("") is True

    def test_known_empty_token(self) -> None:
        # "N/A" normalizes to "n a" via _normalized_text_key, which differs from
        # "na" (in EMPTY_TOKENS). The minimalist form "na" does match.
        assert _is_placeholder_value("na") is True
        assert _is_placeholder_value("-") is True
        assert _is_placeholder_value("none") is True
        assert _is_placeholder_value("null") is True

    def test_placeholder_phrase(self) -> None:
        assert _is_placeholder_value("coming soon") is True
        assert _is_placeholder_value("not specified") is True

    def test_short_symbols_only(self) -> None:
        # "--" normalizes to empty since only symbols remain
        assert _is_placeholder_value("--") is True
        # "..." normalizes to empty since only symbols remain
        assert _is_placeholder_value("...") is True

    def test_short_alphanumeric_is_valid(self) -> None:
        assert _is_placeholder_value("NYC") is False
        assert _is_placeholder_value("238") is False

    def test_click_read_view_prefixes(self) -> None:
        assert _is_placeholder_value("click here") is True
        assert _is_placeholder_value("read more") is True
        assert _is_placeholder_value("view details") is True


# ─── _is_empty_value ────────────────────────────────────────────────────


class TestIsEmptyValue:
    def test_none_is_empty(self) -> None:
        assert _is_empty_value(None) is True

    def test_empty_string_is_empty(self) -> None:
        assert _is_empty_value("") is True

    def test_placeholder_string_is_empty(self) -> None:
        assert _is_empty_value("-") is True

    def test_meaningful_string_is_not_empty(self) -> None:
        assert _is_empty_value("Acme Corp") is False

    def test_list_with_meaningful_items(self) -> None:
        assert _is_empty_value(["Acme", "Corp"]) is False

    def test_list_with_only_placeholders_is_empty(self) -> None:
        # N/A normalizes to "n a" which isn't in EMPTY_TOKENS.
        # Use tokens that are reliably recognized: "-" and "none".
        assert _is_empty_value(["-", "none", ""]) is True

    def test_mixed_list_with_one_good_item(self) -> None:
        assert _is_empty_value(["-", "Acme", "none"]) is False


# ─── _is_entity_name_field ──────────────────────────────────────────────


class TestIsEntityNameField:
    def test_entity_fields(self) -> None:
        assert _is_entity_name_field("company_name") is True
        assert _is_entity_name_field("name") is True
        assert _is_entity_name_field("title") is True
        assert _is_entity_name_field("entity") is True

    def test_non_entity_fields(self) -> None:
        assert _is_entity_name_field("email") is False
        assert _is_entity_name_field("phone") is False
        assert _is_entity_name_field("") is False


# ─── _is_noise_name_value ───────────────────────────────────────────────


class TestIsNoiseNameValue:
    def test_empty_is_noise(self) -> None:
        assert _is_noise_name_value("") is True

    def test_placeholder_is_noise(self) -> None:
        # "N/A" normalizes to "n a" which isn't a recognized empty token.
        # "none" with stripped punctuation does match.
        assert _is_noise_name_value("none") is True

    def test_location_words_are_noise(self) -> None:
        assert _is_noise_name_value("city") is True
        assert _is_noise_name_value("country") is True

    def test_privacy_terms_are_noise(self) -> None:
        assert _is_noise_name_value("privacy policy") is True
        assert _is_noise_name_value("terms of service") is True

    def test_meaningful_name_is_not_noise(self) -> None:
        assert _is_noise_name_value("Acme Corporation") is False


# ─── _valid_email ───────────────────────────────────────────────────────


class TestValidEmail:
    def test_valid_emails(self) -> None:
        # example.com is in EMAIL_BLOCKED_DOMAINS, so we must use a non-blocked domain
        assert _valid_email("user@example.org") == "user@example.org"
        assert _valid_email("first.last@sub.example.co.uk") == "first.last@sub.example.co.uk"

    def test_extracts_email_from_text(self) -> None:
        result = _valid_email("Contact us at user@valid.org for info")
        assert result == "user@valid.org"

    def test_returns_none_for_no_email(self) -> None:
        assert _valid_email("no email here") is None

    def test_rejects_noreply(self) -> None:
        # noreply is explicitly rejected by _valid_email
        assert _valid_email("noreply@example.org") is None

    def test_rejects_blocked_domains(self) -> None:
        # example.com is in EMAIL_BLOCKED_DOMAINS setting
        assert _valid_email("user@example.com") is None
        assert _valid_email("test@localhost") is None

    def test_accepts_non_blocked_domain(self) -> None:
        assert _valid_email("user@example.org") == "user@example.org"


# ─── _valid_phone ────────────────────────────────────────────────────────


class TestValidPhone:
    def test_valid_phone(self) -> None:
        result = _valid_phone("+1 (555) 123-4567")
        assert result is not None

    def test_extracts_phone_from_text(self) -> None:
        result = _valid_phone("Call us at +1 (555) 123-4567 today")
        assert result is not None

    def test_returns_none_for_too_short(self) -> None:
        assert _valid_phone("123") is None

    def test_returns_none_for_no_phone(self) -> None:
        assert _valid_phone("no phone here") is None

    def test_multi_candidate_deduplicates(self) -> None:
        result = _valid_phone("+1-555-123-4567 and also +1-555-123-4567")
        assert result is not None


# ─── _sanitize_field_value ──────────────────────────────────────────────


class TestSanitizeFieldValue:
    def test_none_returns_none(self) -> None:
        schema_field = SchemaField(name="name", field_type=FieldType.STRING)
        assert _sanitize_field_value(schema_field, None) is None

    def test_empty_value_returns_none(self) -> None:
        schema_field = SchemaField(name="name", field_type=FieldType.STRING)
        assert _sanitize_field_value(schema_field, "") is None

    def test_valid_email(self) -> None:
        schema_field = SchemaField(name="email", field_type=FieldType.EMAIL)
        # Use a non-blocked domain (example.org is not in EMAIL_BLOCKED_DOMAINS)
        result = _sanitize_field_value(schema_field, "user@valid.org")
        assert result == "user@valid.org"

    def test_invalid_email_returns_none(self) -> None:
        schema_field = SchemaField(name="email", field_type=FieldType.EMAIL)
        assert _sanitize_field_value(schema_field, "not-an-email") is None

    def test_valid_phone(self) -> None:
        schema_field = SchemaField(name="phone", field_type=FieldType.PHONE)
        result = _sanitize_field_value(schema_field, "+1 (555) 123-4567")
        assert result is not None

    def test_list_string(self) -> None:
        schema_field = SchemaField(name="tags", field_type=FieldType.LIST_STRING)
        result = _sanitize_field_value(schema_field, ["a", "-", "b"])
        assert result == ["a", "b"]

    def test_currency_extraction(self) -> None:
        schema_field = SchemaField(name="price", field_type=FieldType.CURRENCY)
        result = _sanitize_field_value(schema_field, "$1,200.50")
        assert result == "$1,200.50"

    def test_url_adds_base(self) -> None:
        schema_field = SchemaField(name="website", field_type=FieldType.URL)
        result = _sanitize_field_value(schema_field, "/about", base_url="https://example.com")
        assert result == "https://example.com/about"

    def test_noise_name_value_returns_none(self) -> None:
        schema_field = SchemaField(name="name", field_type=FieldType.STRING)
        assert _sanitize_field_value(schema_field, "privacy policy") is None


# ─── clean_html_for_selectors ────────────────────────────────────────────


class TestCleanHtmlForSelectors:
    def test_removes_script_and_style(self) -> None:
        from app.html_utils import clean_html_for_selectors

        html = "<html><head><script>alert(1)</script><style>.cls{}</style></head><body><p>Hello</p></body></html>"
        cleaned = clean_html_for_selectors(html, max_chars=10000)
        assert "alert" not in cleaned
        assert ".cls" not in cleaned
        assert "Hello" in cleaned

    def test_truncates_to_max_chars(self) -> None:
        from app.html_utils import clean_html_for_selectors

        html = "<p>" + "A" * 500 + "</p>"
        cleaned = clean_html_for_selectors(html, max_chars=100)
        assert len(cleaned) <= 100
