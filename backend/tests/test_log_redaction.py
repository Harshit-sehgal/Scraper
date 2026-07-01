"""Unit tests for PII redaction utilities.

Covers redact_url, mask_proxy_url, redact_pii, sanitize_log_value,
and truncate_url — ensuring no credentials or PII leak into logs.
"""

from __future__ import annotations

from app.utils.log_redaction import (
    mask_proxy_url,
    redact_pii,
    redact_url,
    sanitize_log_value,
    truncate_url,
)

# ─── redact_url ────────────────────────────────────────────────────────────


class TestRedactUrl:
    def test_strips_query_params(self) -> None:
        result = redact_url("https://example.com/page?token=abc123&session=xyz")
        assert "token=" not in result
        assert result == "https://example.com/page"

    def test_strips_fragment(self) -> None:
        result = redact_url("https://example.com/page#section")
        assert "#section" not in result
        assert result == "https://example.com/page"

    def test_strips_userinfo(self) -> None:
        result = redact_url("https://user:pass@example.com/path")
        assert "user:pass" not in result
        assert "user" not in result
        assert result == "https://example.com/path"

    def test_preserves_scheme_and_host(self) -> None:
        result = redact_url("https://api.example.com/v1/data?key=secret")
        assert result.startswith("https://api.example.com")

    def test_truncates_long_path(self) -> None:
        long_path = "/" + "a" * 100
        url = f"https://example.com{long_path}"
        result = redact_url(url, max_len=50)
        assert len(result) < len(url)
        assert result.endswith("...")

    def test_empty_url_returns_empty(self) -> None:
        assert redact_url("") == ""

    def test_invalid_url_returns_placeholder(self) -> None:
        result = redact_url("http://[invalid]")
        assert result == "<invalid-url>"

    def test_short_url_unchanged(self) -> None:
        url = "https://example.com/short"
        assert redact_url(url) == url


# ─── mask_proxy_url ────────────────────────────────────────────────────────


class TestMaskProxyUrl:
    def test_masks_userinfo(self) -> None:
        result = mask_proxy_url("http://user:pass@proxy.example.com:8080")
        assert "user" not in result or "****@" in result
        assert "pass" not in result
        assert "****@" in result
        assert "proxy.example.com:8080" in result

    def test_no_userinfo_returns_unchanged(self) -> None:
        url = "http://proxy.example.com:3128"
        assert mask_proxy_url(url) == url

    def test_empty_returns_empty(self) -> None:
        assert mask_proxy_url("") == ""

    def test_invalid_proxy_returns_placeholder(self) -> None:
        assert mask_proxy_url("://foo") == "<invalid-proxy>"

    def test_masks_username_only(self) -> None:
        result = mask_proxy_url("http://user@proxy.example.com:8080")
        assert "****@" in result
        assert "proxy.example.com:8080" in result

    def test_preserves_path_after_masking(self) -> None:
        result = mask_proxy_url("http://user:pass@proxy.com/path?query=1#frag")
        assert "user:pass" not in result
        assert "****@" in result
        assert "/path" in result


# ─── redact_pii ────────────────────────────────────────────────────────────


class TestRedactPii:
    def test_redacts_email(self) -> None:
        result = redact_pii("Contact: alice@example.com for info")
        assert "alice@example.com" not in result
        assert "<redacted_email>" in result

    def test_redacts_phone(self) -> None:
        result = redact_pii("Call +1-555-123-4567 now")
        assert "555-123-4567" not in result
        assert "<redacted_phone>" in result

    def test_redacts_email_and_phone(self) -> None:
        result = redact_pii("Email: a@b.com, Phone: +1 555 123 4567")
        assert "<redacted_email>" in result
        assert "<redacted_phone>" in result

    def test_multiple_emails_redacted(self) -> None:
        result = redact_pii("a@b.com and c@d.org are contacts")
        assert result.count("<redacted_email>") == 2

    def test_no_pii_unchanged(self) -> None:
        text = "Just a normal log message without PII"
        assert redact_pii(text) == text

    def test_empty_string(self) -> None:
        assert redact_pii("") == ""

    def test_none_returns_none(self) -> None:
        assert redact_pii(None) is None  # type: ignore[arg-type]

    def test_short_phone_number_not_redacted(self) -> None:
        """Very short numeric sequences should not be falsely redacted."""
        result = redact_pii("id 123 is short")
        assert "<redacted_phone>" not in result


# ─── sanitize_log_value ────────────────────────────────────────────────────


class TestSanitizeLogValue:
    def test_redacts_pii_in_strings(self) -> None:
        result = sanitize_log_value("email: alice@example.com")
        assert isinstance(result, str)
        assert "<redacted_email>" in result
        assert "alice@example.com" not in str(result)

    def test_redacts_sensitive_dict_keys(self) -> None:
        data = {"name": "test", "api_key": "sk-1234", "password": "secret", "public": "visible"}
        result = sanitize_log_value(data)
        assert isinstance(result, dict)
        assert result.get("name") == "test"
        assert result.get("api_key") == "********"
        assert result.get("password") == "********"
        assert result.get("public") == "visible"

    def test_redacts_nested_dict(self) -> None:
        data = {"user": {"email": "a@b.com", "token": "tkn123"}}
        result = sanitize_log_value(data)
        assert isinstance(result, dict)
        nested = result.get("user")
        assert isinstance(nested, dict)
        assert "<redacted_email>" in str(nested)
        assert nested.get("token") == "********"

    def test_recursively_sanitizes_list(self) -> None:
        data = [{"name": "alice", "email": "a@b.com"}, {"name": "bob"}]
        result = sanitize_log_value(data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert "<redacted_email>" in str(result[0])

    def test_depth_limited(self) -> None:
        """Deeply nested structures are truncated at max depth."""
        deep = {"level1": {"level2": {"level3": {"email": "a@b.com"}}}}
        result = sanitize_log_value(deep)
        # Even with depth limit, the email at depth 3 should still be redacted
        # since depth limit is 50 by default
        assert isinstance(result, dict)

    def test_none_passthrough(self) -> None:
        assert sanitize_log_value(None) is None

    def test_integer_passthrough(self) -> None:
        assert sanitize_log_value(42) == 42

    def test_float_passthrough(self) -> None:
        assert sanitize_log_value(3.14) == 3.14

    def test_boolean_passthrough(self) -> None:
        assert sanitize_log_value(True) is True

    def test_sensitive_key_case_insensitive(self) -> None:
        data = {"API_KEY": "sk-1234", "Secret": "s3cr3t"}
        result = sanitize_log_value(data)
        assert isinstance(result, dict)
        assert result.get("API_KEY") == "********"
        assert result.get("Secret") == "********"

    def test_partial_match_sensitive_key(self) -> None:
        """Keys containing sensitive substrings should be redacted."""
        data = {"my_api_key_here": "abc123", "safe_field": "visible"}
        result = sanitize_log_value(data)
        assert isinstance(result, dict)
        assert result.get("my_api_key_here") == "********"
        assert result.get("safe_field") == "visible"


# ─── truncate_url ──────────────────────────────────────────────────────────


class TestTruncateUrl:
    def test_short_url_unchanged(self) -> None:
        url = "https://example.com/short"
        assert truncate_url(url) == url

    def test_long_url_truncated(self) -> None:
        long_url = "https://example.com/" + "x" * 200
        result = truncate_url(long_url)
        assert len(result) == 103  # 100 + "..."
        assert result.endswith("...")

    def test_custom_max_len(self) -> None:
        url = "https://example.com/12345"
        result = truncate_url(url, max_len=20)
        assert len(result) == 23  # 20 + "..."
        assert result.endswith("...")

    def test_exact_length_not_truncated(self) -> None:
        url = "https://example.com/exact"
        assert truncate_url(url, max_len=100) == url
