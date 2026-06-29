from __future__ import annotations

import uuid

from app.middlewares import _is_safe_request_id


class TestRequestIdMiddleware:
    def test_safe_request_id_alpha(self) -> None:
        assert _is_safe_request_id("abc123") is True

    def test_safe_request_id_with_hyphen(self) -> None:
        assert _is_safe_request_id("req-123-abc") is True

    def test_safe_request_id_with_underscore(self) -> None:
        assert _is_safe_request_id("req_123") is True

    def test_safe_request_id_with_dot(self) -> None:
        assert _is_safe_request_id("1.2.3") is True

    def test_rejects_empty_string(self) -> None:
        assert _is_safe_request_id("") is False

    def test_rejects_crlf(self) -> None:
        assert _is_safe_request_id("abc\r\n") is False

    def test_rejects_space(self) -> None:
        assert _is_safe_request_id("abc def") is False

    def test_rejects_long_value(self) -> None:
        assert _is_safe_request_id("x" * 200) is False

    def test_uuid4_is_always_safe(self) -> None:
        rid = uuid.uuid4().hex
        assert _is_safe_request_id(rid) is True

    def test_rejects_non_string(self) -> None:
        assert _is_safe_request_id(None) is False  # type: ignore[arg-type]
        assert _is_safe_request_id(123) is False  # type: ignore[arg-type]
