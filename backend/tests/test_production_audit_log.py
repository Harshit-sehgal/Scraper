from __future__ import annotations

import json

import pytest
from app.audit_logger import (
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
def _reset_audit(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AUDIT_LOG_DIR", str(tmp_path))
    reset_audit_logger()
    yield
    reset_audit_logger()


def _check_audit_log_contains(text: str) -> bool:
    events = get_recent_events(100)
    return any(text in json.dumps(e) for e in events)


class TestAuditLogger:
    def test_log_auth_event_writes_to_audit(self) -> None:
        log_auth_event("test_user", "login", resource="/api/session", outcome="success")
        events = get_recent_events(10)
        assert len(events) >= 1
        latest = events[0]
        assert latest["event_type"] == "auth"
        assert latest["actor"] == "test_user"
        assert latest["action"] == "login"

    def test_log_rbac_event_writes_to_audit(self) -> None:
        log_rbac_event("user1", "delete_job", "job:123", role="admin", outcome="denied")
        events = get_recent_events(10)
        assert any(e["event_type"] == "rbac" for e in events)

    def test_log_job_event_writes_to_audit(self) -> None:
        log_job_event("user1", "created", "job-abc-123")
        events = get_recent_events(10)
        assert any(e["event_type"] == "job" for e in events)

    def test_log_data_access_writes_to_audit(self) -> None:
        log_data_access("user1", "export_csv", resource="job:456")
        events = get_recent_events(10)
        assert any(e["event_type"] == "data_access" for e in events)

    def test_log_system_event_writes_to_audit(self) -> None:
        log_system_event("startup", resource="system")
        events = get_recent_events(10)
        assert any(e["event_type"] == "system" for e in events)

    def test_log_admin_action_writes_to_audit(self) -> None:
        log_admin_action("admin1", "config_change", resource="rate_limits")
        events = get_recent_events(10)
        assert any(e["event_type"] == "admin" for e in events)

    def test_parse_audit_log_line_valid(self) -> None:
        line = '{"event_type":"auth","action":"test","actor":"u"}'
        parsed = _parse_audit_log_line(line)
        assert parsed is not None
        assert parsed["event_type"] == "auth"

    def test_parse_audit_log_line_invalid(self) -> None:
        assert _parse_audit_log_line("not json") is None

    def test_audit_event_has_correct_shape(self) -> None:
        event = AuditEvent("auth", "actor1", "login", resource="/test", details={"key": "val"}, outcome="success")
        d = event.to_dict()
        assert "timestamp" in d
        assert "iso_time" in d
        assert d["event_type"] == "auth"
        assert d["actor"] == "actor1"
        assert d["action"] == "login"
        assert d["resource"] == "/test"
        assert d["outcome"] == "success"
        assert d["details"] == {"key": "val"}

    def test_audit_event_to_log_line_is_json(self) -> None:
        event = AuditEvent("system", "system", "startup", resource="system")
        line = event.to_log_line()
        parsed = json.loads(line)
        assert parsed["event_type"] == "system"
