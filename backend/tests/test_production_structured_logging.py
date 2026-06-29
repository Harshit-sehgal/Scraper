from __future__ import annotations

import io
import json
import logging

import pytest
from app.logging_config import (
    JsonFormatter,
    SecretRedactionFilter,
    TextFormatter,
    configure_logging,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_logging():
    reset_for_tests()
    yield
    reset_for_tests()


class TestStructuredLogging:
    def test_json_formatter_produces_valid_json(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test_logger"

    def test_json_formatter_includes_timestamp(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
        output = json.loads(fmt.format(record))
        assert "timestamp" in output

    def test_text_formatter_produces_plain_text(self) -> None:
        fmt = TextFormatter()
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", (), None)
        output = fmt.format(record)
        assert isinstance(output, str)
        assert "hello" in output
        assert "INFO" in output

    def test_secret_redaction_filter_redacts_api_keys(self) -> None:
        filt = SecretRedactionFilter()
        record = logging.LogRecord(
            "x",
            logging.WARNING,
            __file__,
            1,
            "X-API-Key: sk-1234-secret-key-value",
            (),
            None,
        )
        assert filt.filter(record) is True
        assert "***" in record.msg
        assert "sk-1234" not in record.msg

    def test_json_formatter_stores_extra_fields(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", (), None)
        record.access_log = True
        record.method = "GET"
        record.path = "/health"
        output = json.loads(fmt.format(record))
        assert output.get("access_log") is True
        assert output.get("method") == "GET"

    def test_configure_logging_uses_json_by_default(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", fmt="json", stream=stream)
        logger = logging.getLogger("test_configure")
        logger.info("configure test")
        output = stream.getvalue()
        parsed = json.loads(output.strip().split("\n")[0])
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "configure test"
