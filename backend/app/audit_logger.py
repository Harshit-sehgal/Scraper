"""\
Audit Logger — structured event logging for security-relevant actions.

Provides a dedicated audit log separate from application logging:
- Authentication events (login success / failure, RBAC violations)
- Administrative actions (job deletion, system config changes)
- Data access events (result exports, sensitive operations)

Uses Python's RotatingFileHandler for log rotation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ─── Constants ─────────────────────────────────────────────────────────────
AUDIT_LOG_DIR = "logs"
AUDIT_LOG_FILE = "audit.log"
AUDIT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
AUDIT_LOG_BACKUP_COUNT = 5

# ─── Module-level logger ──────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── Module-level state ───────────────────────────────────────────────────
_logger: logging.Logger | None = None
_audit_lock = threading.Lock()


def _audit_log_path() -> Path:
    """Resolve the current audit log path from settings or module defaults."""
    try:
        from app.config import settings

        configured_log_dir = settings.AUDIT_LOG_DIR
    except Exception:
        logger.debug("Failed to load AUDIT_LOG_DIR from settings, using default", exc_info=True)
        configured_log_dir = ""
    return Path(configured_log_dir or AUDIT_LOG_DIR) / AUDIT_LOG_FILE


def _normalise_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _has_file_handler(audit_logger: logging.Logger, log_path: Path) -> bool:
    target = _normalise_path(log_path)
    for handler in audit_logger.handlers:
        base_filename = getattr(handler, "baseFilename", "")
        if base_filename and _normalise_path(base_filename) == target:
            return True
    return False


def _add_file_handler(audit_logger: logging.Logger, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=AUDIT_LOG_MAX_BYTES,
        backupCount=AUDIT_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [AUDIT] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    audit_logger.addHandler(handler)


def _get_audit_logger() -> logging.Logger:
    """Get or create the audit logger singleton."""
    global _logger
    if _logger is not None:
        log_path = _audit_log_path()
        if not _has_file_handler(_logger, log_path):
            _add_file_handler(_logger, log_path)
        return _logger
    with _audit_lock:
        if _logger is not None:
            log_path = _audit_log_path()
            if not _has_file_handler(_logger, log_path):
                _add_file_handler(_logger, log_path)
            return _logger

        _logger = logging.getLogger("audit")
        _logger.setLevel(logging.INFO)

        # Prevent the audit logger from propagating to the root logger
        _logger.propagate = False

        # Pytest/logging integrations can attach non-file handlers to the
        # named ``audit`` logger before this singleton is initialized. Do not
        # treat those as audit persistence. Ensure the active log path has a
        # real file handler.
        log_path = _audit_log_path()
        if not _has_file_handler(_logger, log_path):
            _add_file_handler(_logger, log_path)

    return _logger


# ─── Audit Event Types ────────────────────────────────────────────────────


class AuditEvent:
    """Structured audit event with consistent fields."""

    def __init__(
        self,
        event_type: str,
        actor: str,
        action: str,
        resource: str,
        details: dict[str, Any] | None = None,
        outcome: str = "success",
    ) -> None:
        self.timestamp = time.time()
        self.event_type = event_type
        self.actor = actor
        self.action = action
        self.resource = resource
        self.details = details or {}
        self.outcome = outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)),
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "details": self.details,
        }

    def to_log_line(self) -> str:
        """Serialize to a single-line JSON for structured logging."""
        return json.dumps(self.to_dict(), default=str)


# ─── Public API ───────────────────────────────────────────────────────────


def log_auth_event(
    actor: str,
    action: str,
    resource: str = "",
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    *,
    org_id: str = "",
    project_id: str = "",
) -> None:
    """Log an authentication-related event.

    Args:
        actor: The identity attempting authentication (e.g. IP, key prefix)
        action: The auth action (e.g. "login", "logout", "token_refresh")
        resource: Optional resource being accessed
        outcome: "success" or "failure"
        details: Optional additional context
        org_id: P0-SAAS-001 tenant attribution (written into ``details["org_id"]``)
        project_id: P0-SAAS-001 project attribution (written into ``details["project_id"]``)

    """
    merged_details: dict[str, Any] = dict(details or {})
    if org_id:
        merged_details.setdefault("org_id", org_id)
    if project_id:
        merged_details.setdefault("project_id", project_id)
    event = AuditEvent(
        event_type="auth",
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        details=merged_details,
    )
    _get_audit_logger().info(event.to_log_line())


def log_rbac_event(
    actor: str,
    action: str,
    resource: str,
    role: str,
    outcome: str = "denied",
    details: dict[str, Any] | None = None,
) -> None:
    """Log an RBAC authorization event.

    Args:
        actor: The user / role attempting the action
        action: The action attempted (e.g. "delete_job", "create_job")
        resource: The resource being accessed
        role: The role assigned to the actor
        outcome: "granted", "denied", or "escalation"
        details: Optional additional context

    """
    event = AuditEvent(
        event_type="rbac",
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        details={**(details or {}), "role": role},
    )
    _get_audit_logger().info(event.to_log_line())


def log_admin_action(
    actor: str,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an administrative action.

    Args:
        actor: The admin identity
        action: The action performed
        resource: The resource affected
        details: Optional additional context

    """
    event = AuditEvent(
        event_type="admin",
        actor=actor,
        action=action,
        resource=resource,
        outcome="success",
        details=details,
    )
    _get_audit_logger().info(event.to_log_line())


def log_data_access(
    actor: str,
    action: str,
    resource: str,
    details: dict[str, Any] | None = None,
    outcome: str = "success",
    *,
    org_id: str = "",
    project_id: str = "",
) -> None:
    """Log a data access event (exports, sensitive reads).

    Args:
        actor: The identity accessing data
        action: The access action (e.g. "export_csv", "export_json")
        resource: The resource being accessed
        details: Optional additional context
        outcome: The outcome of the access (success or failure)
        org_id: P0-SAAS-001 tenant attribution
        project_id: P0-SAAS-001 project attribution

    """
    merged_details: dict[str, Any] = dict(details or {})
    if org_id:
        merged_details.setdefault("org_id", org_id)
    if project_id:
        merged_details.setdefault("project_id", project_id)
    event = AuditEvent(
        event_type="data_access",
        actor=actor,
        action=action,
        resource=resource,
        outcome=outcome,
        details=merged_details,
    )
    _get_audit_logger().info(event.to_log_line())


def log_job_event(
    actor: str,
    action: str,
    job_id: str,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    *,
    org_id: str = "",
    project_id: str = "",
) -> None:
    """Log a job lifecycle event.

    Args:
        actor: The identity that triggered the event
        action: The job action (e.g. "created", "canceled", "deleted")
        job_id: The job ID
        outcome: "success" or "failure"
        details: Optional additional context
        org_id: P0-SAAS-001 tenant attribution
        project_id: P0-SAAS-001 project attribution

    """
    merged_details: dict[str, Any] = dict(details or {})
    if org_id:
        merged_details.setdefault("org_id", org_id)
    if project_id:
        merged_details.setdefault("project_id", project_id)
    event = AuditEvent(
        event_type="job",
        actor=actor,
        action=action,
        resource=f"job:{job_id}",
        outcome=outcome,
        details=merged_details,
    )
    _get_audit_logger().info(event.to_log_line())


def log_system_event(
    action: str,
    resource: str = "",
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    """Log a system-level event (startup, shutdown, config change).

    Args:
        action: The system action
        resource: Optional resource affected
        outcome: "success" or "failure"
        details: Optional additional context

    """
    event = AuditEvent(
        event_type="system",
        actor="system",
        action=action,
        resource=resource,
        outcome=outcome,
        details=details,
    )
    _get_audit_logger().info(event.to_log_line())


# ─── Validation ───────────────────────────────────────────────────────────


def _parse_audit_log_line(line: str) -> dict[str, Any] | None:
    """Parse a single audit log line back into a dictionary.

    Useful for testing and log analysis.
    """
    try:
        if "[AUDIT]" in line:
            json_start = line.index("[AUDIT]") + len("[AUDIT] ")
            return json.loads(line[json_start:])  # type: ignore[no-any-return]
        return json.loads(line)  # type: ignore[no-any-return]
    except (ValueError, json.JSONDecodeError):
        return None


def get_audit_log_path() -> Path:
    """Get the current audit log file path."""
    return _audit_log_path()


def get_recent_events(count: int = 50) -> list[dict[str, Any]]:
    """Return the most recent audit events from the log file.

    Args:
        count: Maximum number of events to return

    Returns:
        List of parsed audit event dictionaries, most recent first

    """
    log_path = get_audit_log_path()
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        from collections import deque

        def _parse_lines(f):
            for raw in f:
                stripped = raw.strip()
                if stripped:
                    parsed = _parse_audit_log_line(stripped)
                    if parsed:
                        yield parsed

        with open(log_path, encoding="utf-8") as f:
            recent = deque(_parse_lines(f), maxlen=count)
            events = list(recent)
    except OSError as e:
        logger.warning("Failed to read audit log: %s", e)
        return []

    return list(reversed(events[-count:]))


def reset_audit_logger() -> None:
    """Reset the audit logger singleton (for testing)."""
    global _logger
    if _logger:
        for handler in list(_logger.handlers):
            handler.close()
        _logger.handlers.clear()
    _logger = None
