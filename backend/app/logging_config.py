"""Centralized Logging Configuration for DataForge Scraper.

Provides:

1. ``DictConfig`` JSON formatter + stdout handler — container-friendly output
   suitable for log aggregators (Loki, ELK, CloudWatch Logs, etc.).
2. Secret-redaction filter — strips API keys, tokens, passwords from log
   records before they reach the formatter.
3. Structured ``extra``-fields pass-through so the ``access_log_middleware``
   can emit per-request JSON lines that include method, path, status, latency.
4. Honour owner-controlled ``DATAFORGE_LOG_LEVEL`` and
   ``DATAFORGE_LOG_FORMAT`` settings at startup.
5. Replace the previous "claim JSON output, emit raw Python LogRecord"
   pattern that left the access log middleware misleading.

Public API:

- :func:`configure_logging` — idempotent at-call-side-safe setup
- :func:`JsonFormatter` — the JSON line formatter
- :func:`SecretRedactionFilter` — replaces known-sensitive values

The module is import-safe even when Django-style logging is not yet configured.
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import re
import sys
from datetime import UTC, datetime
from typing import Any

# ─── Defaults ──────────────────────────────────────────────────────────────
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "json"  # "json" | "text"

# Recognised log levels
_VALID_LEVELS = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
)

# Patterns we redact from log records.  Each entry is a compiled regex
# matched against the rendered log message; when matched, the secret is
# replaced with a `***` placeholder.  Compiled at import time so the
# cost is paid once.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # API key header values: "X-API-Key: <value>" → "X-API-Key: ***"
    re.compile(r"(X-API-[Kk]ey:\s*)([^\s,;\"']+)"),
    # Bearer tokens
    re.compile(r"(Authorization:\s*Bearer\s+)([A-Za-z0-9._\-+/=]{8,})"),
    # Groq / OpenAI style keys
    re.compile(r"(gsk_[A-Za-z0-9_\-]{20,})"),
    # Cookie set-cookie values
    re.compile(r"(Set-Cookie:\s*)([^;]+)", re.IGNORECASE),
    # URL with embedded credentials: user:pass@host
    re.compile(r"(https?://)([^\s/@]+):([^\s/@]+)@"),
)


class SecretRedactionFilter(logging.Filter):
    """Logging filter that redacts known-sensitive values from log records.

    Inspects the formatted-message area (``record.getMessage()``) and any
    string values in ``record.args``.  The replacement is applied to
    ``record.msg`` only — the raw ``args`` survive unmodified so the
    caller can still format their own messages with the original value.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = _redact_secrets(msg)
            if redacted != msg:
                # Apply by re-setting the msg without altering args tuple
                record.msg = redacted
                record.args = ()
        except (AttributeError, ValueError):
            # Never let a logging filter raise — log records must pass
            pass
        return True


def _redact_secrets(text: str) -> str:
    """Apply all secret-redaction patterns to ``text``."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_redact_match, text)
    return text


def _redact_match(match: re.Match[str]) -> str:
    """Replace the matched groups with placeholders, preserving the
    prefix group (e.g. ``"X-API-Key: "``) so operators can still see
    which field carried the redacted value.
    """
    if match.lastindex and match.lastindex >= 1:
        groups = match.groups()
        # Preserve first 1-2 groups (prefix info), redact everything else
        preserved = " ".join(g for g in groups[:-1] if g)
        if preserved:
            return f"{preserved} ***"
    return "***"


class JsonFormatter(logging.Formatter):
    """JSON line formatter — one JSON object per log line.

    Captures the standard LogRecord fields plus any keys added via the
    ``extra`` argument (``method``, ``path``, ``status``, ``latency_ms``,
    ``client_ip``, ``trace_id``, ``access_log: True``, etc.).  When the
    record originated from the access log middleware, all ``extra`` keys
    become top-level fields in the JSON output, not buried in a nested
    object.
    """

    # Standard LogRecord fields we promote to top-level JSON keys
    _STANDARD_FIELDS = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
            "message",
            "asctime",
        },
    )

    def format(self, record: logging.LogRecord) -> str:
        # Build the canonical payload
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        # Promote everything passed via ``extra=`` to top-level fields.
        # This is how the access_log_middleware's method/path/status/
        # latency_ms end up in the structured JSON line.
        for key, value in record.__dict__.items():
            if key in self._STANDARD_FIELDS or key.startswith("_"):
                continue
            if key == "access_log":
                # Marker flag — encode as boolean instead of leaving "True" stringy
                payload["access_log"] = bool(value)
                continue
            # Try to be JSON-friendly; fall back to str()
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)

        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            # Last-resort: quote everything
            return json.dumps({k: str(v) for k, v in payload.items()})


class TextFormatter(logging.Formatter):
    """Plain-text formatter, container-friendly.  Used when
    ``DATAFORGE_LOG_FORMAT=text``.
    """

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )


_configured = False
_configured_lock = False  # cheap idempotency guard


def configure_logging(
    level: str | None = None,
    fmt: str | None = None,
    stream = None,
) -> None:
    """Configure root logging based on settings / explicit args.

    Args:
        level: One of ``DEBUG/INFO/WARNING/ERROR/CRITICAL``.  Falls back
            to ``DATAFORGE_LOG_LEVEL`` env var, then ``INFO``.
        fmt: ``"json"`` or ``"text"``.  Falls back to ``DATAFORGE_LOG_FORMAT``
            env var, then ``"json"``.
        stream: IO stream to write to.  Defaults to ``sys.stdout`` for
            container-friendly output.

    Idempotent — calling multiple times does not stack handlers because
    we check ``root.handlers`` and bail out once configuration has been
    applied.
    """
    global _configured
    if _configured:
        return

    # Resolve effective level and format
    effective_level = (level or os.environ.get("DATAFORGE_LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper()
    if effective_level not in _VALID_LEVELS:
        effective_level = DEFAULT_LOG_LEVEL
    effective_format = (fmt or os.environ.get("DATAFORGE_LOG_FORMAT") or DEFAULT_LOG_FORMAT).lower()
    if effective_format not in {"json", "text"}:
        effective_format = DEFAULT_LOG_FORMAT
    if stream is None:
        stream = sys.stdout

    formatter: logging.Formatter
    formatter = JsonFormatter() if effective_format == "json" else TextFormatter()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.addFilter(SecretRedactionFilter())
    handler.setLevel(getattr(logging, effective_level))

    root = logging.getLogger()
    # Clear existing handlers to avoid duplicate output when this function
    # is called more than once (e.g. tests when reloading the module)
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, effective_level))

    # Quiet down chatty third-party loggers by default
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(max(getattr(logging, effective_level), logging.WARNING))

    _configured = True


def reset_for_tests() -> None:
    """Reset configuration so tests can re-apply.  Internal use only."""
    global _configured
    _configured = False
