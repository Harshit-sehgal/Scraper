"""Tests for the centralised logging_config module.

Verifies:
- JSON formatter produces parseable one-line JSON
- Plain text formatter falls back when DATAFORGE_LOG_FORMAT=text
- Secret-redaction filter masks API keys, bearer tokens, embedded URL creds
- ``extra`` dict fields become top-level JSON keys (used by access log middleware)
- Idempotent configuration — repeated calls do not stack handlers
"""
from __future__ import annotations

import io
import json
import logging
from collections.abc import Generator

import pytest
from app.logging_config import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    JsonFormatter,
    SecretRedactionFilter,
    TextFormatter,
    _redact_secrets,
    configure_logging,
    reset_for_tests,
)


@pytest.fixture
def reset_logging_state() -> Generator[None, None, None]:
    """Reset module state before each test."""
    reset_for_tests()
    yield
    reset_for_tests()


# ─── JSON formatter ──────────────────────────────────────────────────────


def test_json_formatter_emits_valid_json(reset_logging_state):
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="/app/x.py",
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    line = formatter.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["message"] == "hello world"


def test_json_formatter_promotes_extras(reset_logging_state):
    """``extra={...}`` keys become top-level JSON fields."""
    formatter = JsonFormatter()
    record = logging.makeLogRecord(
        {
            "name": "access",
            "level": logging.INFO,
            "pathname": "/app/main.py",
            "lineno": 5,
            "msg": "%s on %s",
            "args": ("GET", "/api/health"),
            "access_log": True,
            "method": "GET",
            "path": "/api/health",
            "status": 200,
            "latency_ms": 12.3,
            "client_ip": "127.0.0.1",
        },
    )
    line = formatter.format(record)
    parsed = json.loads(line)
    assert parsed["access_log"] is True
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/api/health"
    assert parsed["status"] == 200
    assert parsed["latency_ms"] == 12.3
    assert parsed["message"] == "GET on /api/health"


def test_json_formatter_includes_exception(reset_logging_state):
    formatter = JsonFormatter()
    try:
        msg = "boom"
        raise ValueError(msg)
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="err",
            level=logging.ERROR,
            pathname="x",
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    line = formatter.format(record)
    parsed = json.loads(line)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]
    assert "boom" in parsed["exception"]


# ─── Text formatter ──────────────────────────────────────────────────────


def test_text_formatter_includes_message(reset_logging_state):
    formatter = TextFormatter()
    record = logging.LogRecord(
        name="t",
        level=logging.WARNING,
        pathname="x",
        lineno=1,
        msg="warning %s",
        args=("msg",),
        exc_info=None,
    )
    line = formatter.format(record)
    assert "WARNING t warning msg" in line


# ─── Secret redaction ────────────────────────────────────────────────────


def test_redact_api_key_header():
    msg = "request failed X-API-Key: abc123def456ghi789jkl012mno345pqr678"
    redacted = _redact_secrets(msg)
    assert "abc123" not in redacted
    assert "***" in redacted
    assert "X-API-Key:" in redacted


def test_redact_bearer_token():
    msg = "auth header Authorization: Bearer eyJhbGciOiJIabcdefghij"
    redacted = _redact_secrets(msg)
    assert "eyJhbGciOiJI" not in redacted
    assert "***" in redacted


def test_redact_url_with_credentials():
    msg = "fetching https://user:password@example.com/page"
    redacted = _redact_secrets(msg)
    assert "password" not in redacted
    assert "user:" not in redacted
    assert "***" in redacted


def test_redact_filter_does_not_drop_record():
    """SecretRedactionFilter must always return True (never drop records)."""
    flt = SecretRedactionFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg="X-API-Key: super-secret-12345",
        args=(),
        exc_info=None,
    )
    assert flt.filter(record) is True


# ─── configure_logging ───────────────────────────────────────────────────


def test_configure_logging_writes_to_stream_as_json(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_LEVEL", "INFO")
    monkeypatch.setenv("DATAFORGE_LOG_FORMAT", "json")
    stream = io.StringIO()
    configure_logging(stream=stream)
    logging.getLogger("test.audit").info(
        "structured",
        extra={"access_log": True, "path": "/api/health", "status": 200, "latency_ms": 5.0},
    )
    output = stream.getvalue()
    assert output  # something was written
    parsed = json.loads(output.strip().splitlines()[-1])
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "structured"
    assert parsed["access_log"] is True
    assert parsed["path"] == "/api/health"
    assert parsed["status"] == 200
    assert parsed["latency_ms"] == 5.0


def test_configure_logging_idempotent(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_FORMAT", "json")
    stream1 = io.StringIO()
    stream2 = io.StringIO()
    configure_logging(stream=stream1)
    initial_handler_count = len(logging.getLogger().handlers)
    configure_logging(stream=stream2)
    after_handler_count = len(logging.getLogger().handlers)
    assert initial_handler_count == after_handler_count, (
        "Reconfiguring logging must not stack handlers"
    )


def test_configure_logging_redacts_in_output(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_FORMAT", "json")
    stream = io.StringIO()
    configure_logging(stream=stream)
    logging.getLogger("t").info("X-API-Key: sk-abcdefghijklmnopqrstuvwxyz")
    out = stream.getvalue()
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out
    assert "***" in out


def test_text_format_fallback(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_FORMAT", "text")
    stream = io.StringIO()
    configure_logging(stream=stream)
    logging.getLogger("t").info("plain")
    out = stream.getvalue()
    assert "plain" in out
    # text format should NOT be JSON
    assert "{" not in out.split("plain")[0] or '"level"' not in out


def test_invalid_level_falls_back_to_info(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_LEVEL", "BOGUS")
    configure_logging(stream=io.StringIO())
    assert logging.getLogger().level == logging.INFO


def test_unknown_format_falls_back_to_json(reset_logging_state, monkeypatch):
    monkeypatch.setenv("DATAFORGE_LOG_FORMAT", "xml")
    stream = io.StringIO()
    configure_logging(stream=stream)
    logging.getLogger("t").info("json-fallback")
    parsed = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert parsed["message"] == "json-fallback"


def test_constants():
    assert DEFAULT_LOG_LEVEL == "INFO"
    assert DEFAULT_LOG_FORMAT == "json"
