"""Unit tests for app.utils.log_redaction — PII / credential redaction utilities."""

from typing import Any

from app.utils.log_redaction import (
    mask_proxy_url,
    redact_pii,
    redact_url,
    sanitize_log_value,
    truncate_url,
)

# ── redact_url ───────────────────────────────────────────────────────────


class TestRedactUrl:
    def test_empty_string(self):
        assert redact_url("") == ""

    def test_strips_query_and_fragment(self):
        result = redact_url("https://example.com/path?token=secret#section")
        assert "token" not in result
        assert "secret" not in result
        assert "#section" not in result
        assert "example.com" in result

    def test_strips_embedded_credentials(self):
        result = redact_url("https://user:pass@example.com/path")
        assert "user" not in result
        assert "pass" not in result
        assert "example.com" in result

    def test_preserves_scheme_and_host(self):
        result = redact_url("https://example.com/api/v1/data")
        assert result.startswith("https://")
        assert "example.com" in result

    def test_truncates_long_path(self):
        long_path = "/a" * 100
        result = redact_url(f"https://example.com{long_path}", max_len=20)
        assert "..." in result

    def test_short_path_not_truncated(self):
        result = redact_url("https://example.com/short")
        assert "..." not in result

    def test_invalid_url(self):
        result = redact_url("://broken")
        assert isinstance(result, str)

    def test_preserves_port(self):
        result = redact_url("https://example.com:8443/api")
        assert "8443" in result


# ── mask_proxy_url ───────────────────────────────────────────────────────


class TestMaskProxyUrl:
    def test_empty_string(self):
        assert mask_proxy_url("") == ""

    def test_no_credentials(self):
        result = mask_proxy_url("http://proxy.example.com:8080")
        assert result == "http://proxy.example.com:8080"

    def test_masks_credentials(self):
        result = mask_proxy_url("http://admin:secretpass@proxy.example.com:8080")
        assert "admin" not in result
        assert "secretpass" not in result
        assert "****@" in result
        assert "proxy.example.com" in result

    def test_invalid_proxy(self):
        result = mask_proxy_url("://broken")
        assert isinstance(result, str)


# ── redact_pii ───────────────────────────────────────────────────────────


class TestRedactPii:
    def test_empty_string(self):
        assert redact_pii("") == ""

    def test_email_redacted(self):
        result = redact_pii("Contact user@example.com for info")
        assert "user@example.com" not in result
        assert "<redacted_email>" in result

    def test_phone_redacted(self):
        result = redact_pii("Call +1 (555) 123-4567 now")
        assert "<redacted_phone>" in result

    def test_multiple_emails(self):
        result = redact_pii("a@b.com and c@d.com")
        assert result.count("<redacted_email>") == 2

    def test_no_pii(self):
        text = "This is normal text with no PII"
        assert redact_pii(text) == text


# ── sanitize_log_value ───────────────────────────────────────────────────


class TestSanitizeLogValue:
    def test_string_with_email(self):
        result = str(sanitize_log_value("user@example.com logged in"))
        assert "<redacted_email>" in result

    def test_dict_sensitive_keys_redacted(self):
        data: dict[str, str] = {"authorization": "Bearer token123", "name": "test"}
        result: Any = sanitize_log_value(data)
        assert "authorization" not in result
        assert "********" in result
        assert "name" in result

    def test_dict_api_key_redacted(self):
        data: dict[str, str] = {"api_key": "sk-12345", "url": "https://example.com"}
        result: Any = sanitize_log_value(data)
        has_redacted = any("********" in str(k) for k in result)
        assert has_redacted

    def test_dict_password_redacted(self):
        data: dict[str, str] = {"password": "secret123"}
        result: Any = sanitize_log_value(data)
        assert "password" not in result

    def test_list_items_sanitized(self):
        data = ["user@example.com", "normal text"]
        result: Any = sanitize_log_value(data)
        assert "<redacted_email>" in result[0]
        assert result[1] == "normal text"

    def test_nested_dict_sanitized(self):
        data: dict[str, Any] = {"outer": {"token": "abc123", "email": "user@test.com"}}
        result: Any = sanitize_log_value(data)
        assert "token" not in result["outer"]

    def test_depth_limit(self):
        deeply_nested: Any = "leaf"
        for _ in range(60):
            deeply_nested = {"key": deeply_nested}
        result = sanitize_log_value(deeply_nested)
        assert result is not None

    def test_non_string_non_dict_passthrough(self):
        assert sanitize_log_value(42) == 42
        assert sanitize_log_value(3.14) == 3.14
        assert sanitize_log_value(None) is None
        assert sanitize_log_value(True) is True


# ── truncate_url ─────────────────────────────────────────────────────────


class TestTruncateUrl:
    def test_short_url_unchanged(self):
        url = "https://example.com"
        assert truncate_url(url) == url

    def test_long_url_truncated(self):
        url = "https://example.com/" + "a" * 200
        result = truncate_url(url, max_len=50)
        assert len(result) == 53  # 50 + "..."
        assert result.endswith("...")

    def test_exact_length_not_truncated(self):
        url = "a" * 100
        assert truncate_url(url, max_len=100) == url
