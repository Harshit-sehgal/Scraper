"""Tests for the audit logger module."""

import json
import tempfile
from pathlib import Path

import pytest
from app.audit_logger import (
    AUDIT_LOG_DIR,
    AUDIT_LOG_FILE,
    AuditEvent,
    _parse_audit_log_line,
    get_recent_events,
    log_admin_action,
    log_auth_event,
    log_data_access,
    log_job_event,
    log_rbac_event,
    log_system_event,
    reset_audit_logger,
)


@pytest.fixture(autouse=True)
def _reset_logger():
    """Reset the audit logger singleton before and after each test."""
    reset_audit_logger()
    yield
    reset_audit_logger()


@pytest.fixture
def temp_log_dir():
    """Temporarily swap the audit log directory to a temp path."""
    original_dir = AUDIT_LOG_DIR
    original_file = AUDIT_LOG_FILE
    with tempfile.TemporaryDirectory() as tmpdir:
        # Monkey-patch the module-level constants by overriding the path
        import app.audit_logger as al

        al.AUDIT_LOG_DIR = tmpdir
        al.AUDIT_LOG_FILE = "test_audit.log"
        # Force re-creation of logger with new path on next access
        reset_audit_logger()
        yield Path(tmpdir)
        # Restore
        al.AUDIT_LOG_DIR = original_dir
        al.AUDIT_LOG_FILE = original_file
        reset_audit_logger()


# ─── AuditEvent Tests ─────────────────────────────────────────────────────


class TestAuditEvent:
    def test_minimal_event(self) -> None:
        event = AuditEvent(
            event_type="auth",
            actor="test-user",
            action="login",
            resource="/api/jobs",
        )
        data = event.to_dict()
        assert data["event_type"] == "auth"
        assert data["actor"] == "test-user"
        assert data["action"] == "login"
        assert data["resource"] == "/api/jobs"
        assert data["outcome"] == "success"
        assert data["details"] == {}
        assert "timestamp" in data
        assert "iso_time" in data

    def test_event_with_details(self) -> None:
        event = AuditEvent(
            event_type="rbac",
            actor="admin",
            action="delete_job",
            resource="job:123",
            details={"job_name": "test", "reason": "cleanup"},
            outcome="denied",
        )
        data = event.to_dict()
        assert data["event_type"] == "rbac"
        assert data["actor"] == "admin"
        assert data["outcome"] == "denied"
        assert data["details"]["job_name"] == "test"

    def test_to_log_line_is_json(self) -> None:
        event = AuditEvent(
            event_type="admin",
            actor="root",
            action="restart",
            resource="system",
        )
        line = event.to_log_line()
        parsed = json.loads(line)
        assert parsed["event_type"] == "admin"
        assert parsed["actor"] == "root"


# ─── Logging Function Tests ──────────────────────────────────────────────


class TestLogFunctions:
    def test_log_auth_event(self, temp_log_dir) -> None:
        log_auth_event(
            actor="127.0.0.1",
            action="api_key_auth",
            resource="/api/jobs",
            outcome="failure",
            details={"reason": "invalid_key"},
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "auth"
        assert events[-1]["actor"] == "127.0.0.1"
        assert events[-1]["outcome"] == "failure"

    def test_log_rbac_event(self, temp_log_dir) -> None:
        log_rbac_event(
            actor="operator-1",
            action="delete_job",
            resource="job:456",
            role="operator",
            outcome="denied",
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "rbac"
        assert events[-1]["details"]["role"] == "operator"
        assert events[-1]["outcome"] == "denied"

    def test_log_admin_action(self, temp_log_dir) -> None:
        log_admin_action(
            actor="admin-1",
            action="purge_jobs",
            resource="system",
            details={"job_count": 42},
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "admin"
        assert events[-1]["action"] == "purge_jobs"
        assert events[-1]["details"]["job_count"] == 42

    def test_log_data_access(self, temp_log_dir) -> None:
        log_data_access(
            actor="user-1",
            action="export_csv",
            resource="job:789",
            details={"format": "csv"},
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "data_access"
        assert events[-1]["action"] == "export_csv"

    def test_log_job_event(self, temp_log_dir) -> None:
        log_job_event(
            actor="admin-1",
            action="created",
            job_id="job-abc-123",
            outcome="success",
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "job"
        assert events[-1]["resource"] == "job:job-abc-123"
        assert events[-1]["action"] == "created"

    def test_log_system_event(self, temp_log_dir) -> None:
        log_system_event(
            action="startup",
            resource="scheduler",
            outcome="success",
        )
        events = get_recent_events(count=10)
        assert len(events) >= 1
        assert events[-1]["event_type"] == "system"
        assert events[-1]["actor"] == "system"
        assert events[-1]["action"] == "startup"

    def test_multiple_events_ordered(self, temp_log_dir) -> None:
        for i in range(5):
            log_auth_event(
                actor=f"user-{i}",
                action="login",
                resource="/api/jobs",
            )
        events = get_recent_events(count=10)
        assert len(events) >= 5
        # Most recent event should be user-4, which is the first element (most recent first)
        assert events[0]["actor"] == "user-4"

    def test_get_recent_events_empty(self, temp_log_dir) -> None:
        """get_recent_events should return empty list when no log file exists."""
        events = get_recent_events(count=10)
        assert events == []

    def test_get_recent_events_limit_and_order(self, temp_log_dir) -> None:
        for i in range(10):
            log_auth_event(
                actor=f"user-{i}",
                action="login",
                resource="/api",
            )
        events = get_recent_events(count=3)
        assert len(events) == 3
        # Verify they are the most recent 3 events, most recent first (user-9, user-8, user-7)
        actors = [e["actor"] for e in events]
        assert actors == ["user-9", "user-8", "user-7"]


# ─── Parse Utility Tests ─────────────────────────────────────────────────


class TestParseFunctions:
    def test_parse_audit_log_line_standard(self) -> None:
        line = (
            "2026-05-30T12:00:00 [AUDIT] {"
            '"event_type":"auth","actor":"test","action":"login",'
            '"resource":"/","outcome":"success","details":{}}'
        )
        parsed = _parse_audit_log_line(line)
        assert parsed is not None
        assert parsed["event_type"] == "auth"
        assert parsed["actor"] == "test"

    def test_parse_audit_log_line_bare_json(self) -> None:
        line = '{"event_type":"auth","actor":"test","action":"login","resource":"/","outcome":"success","details":{}}'
        parsed = _parse_audit_log_line(line)
        assert parsed is not None
        assert parsed["event_type"] == "auth"

    def test_parse_audit_log_line_invalid(self) -> None:
        parsed = _parse_audit_log_line("this is not json")
        assert parsed is None

    def test_parse_audit_log_line_empty(self) -> None:
        parsed = _parse_audit_log_line("")
        assert parsed is None


# ─── Log File Existence Test ─────────────────────────────────────────────


class TestLogFileIO:
    def test_log_file_created(self, temp_log_dir) -> None:
        log_system_event(action="test_startup")
        log_path = temp_log_dir / "test_audit.log"
        assert log_path.exists(), f"Audit log file should exist at {log_path}"
        content = log_path.read_text(encoding="utf-8")
        assert "test_startup" in content

    def test_log_file_rotation(self, temp_log_dir) -> None:
        """Verify that the log file contains properly formatted lines."""
        for i in range(20):
            log_auth_event(actor=f"user-{i}", action="login", resource="/api")
        log_path = temp_log_dir / "test_audit.log"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 20
        for line in lines:
            assert "[AUDIT]" in line


# ─── Thread Safety / Idempotency Tests ───────────────────────────────────


class TestLoggerSingleton:
    def test_logger_is_singleton(self) -> None:
        from app.audit_logger import _get_audit_logger

        logger1 = _get_audit_logger()
        logger2 = _get_audit_logger()
        assert logger1 is logger2

    def test_reset_clears_handlers(self) -> None:
        from app.audit_logger import _get_audit_logger

        logger = _get_audit_logger()
        assert len(logger.handlers) > 0
        old_handler = logger.handlers[0]
        reset_audit_logger()
        # After reset, new logger should have fresh handlers
        new_logger = _get_audit_logger()
        assert len(new_logger.handlers) > 0
        new_handler = new_logger.handlers[0]
        assert new_handler is not old_handler
