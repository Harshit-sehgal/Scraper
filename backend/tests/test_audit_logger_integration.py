"""E2E integration tests for the audit logger middleware.

Verifies that the api_key_middleware in main.py correctly writes audit log
entries for authentication failures and successes.

Uses LocalASGIClient matching the pattern from conftest.py.
"""

import json
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


@pytest.fixture(autouse=True)
def _setup_log_dir():
    """Redirect audit logs to a temp directory for test isolation."""
    import app.audit_logger as al

    original_dir = al.AUDIT_LOG_DIR
    original_file = al.AUDIT_LOG_FILE
    with tempfile.TemporaryDirectory() as tmpdir:
        al.AUDIT_LOG_DIR = tmpdir
        al.AUDIT_LOG_FILE = "test_integration_audit.log"
        al.reset_audit_logger()
        yield Path(tmpdir)
        al.AUDIT_LOG_DIR = original_dir
        al.AUDIT_LOG_FILE = original_file
        al.reset_audit_logger()


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch) -> None:
    """Configure API keys for middleware tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "API_KEY", "test_user_key")
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", "test_operator_key")
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test_admin_key")
    monkeypatch.setattr(settings, "ENV", "testing")


@pytest.fixture
def client(monkeypatch):
    """Create a LocalASGIClient for the app (matching conftest.py pattern)."""
    # Isolate state files via settings
    from app.config import settings

    monkeypatch.setattr(settings, "STATE_FILE_PATH", "/tmp/test_audit_e2e_state.json")  # nosec B108 - hardcoded /tmp path is a test fixture, not production code

    from app.main import app
    from conftest import LocalASGIClient

    return LocalASGIClient(app)


def _read_audit_log(log_dir: Path) -> list[dict]:
    """Read all audit events from the test log file."""
    log_path = log_dir / "test_integration_audit.log"
    if not log_path.exists():
        return []
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line or "[AUDIT]" not in line:
                continue
            try:
                json_start = line.index("[AUDIT]") + len("[AUDIT] ")
                events.append(json.loads(line[json_start:]))
            except (ValueError, json.JSONDecodeError):
                continue
    return events


# ── Auth Failure Tests ───────────────────────────────────────────────────


class TestAuthFailureLogging:
    def test_invalid_api_key_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Invalid API key should log an auth failure event."""
        response = client.get("/api/jobs", headers={"X-API-Key": "invalid_key"})
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
        assert len(events) >= 1
        failure_events = [e for e in events if e["outcome"] == "failure"]
        assert len(failure_events) >= 1
        assert failure_events[0]["event_type"] == "auth"
        assert failure_events[0]["action"] == "api_key_auth"

    def test_missing_api_key_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Missing API key header should log an auth failure event."""
        response = client.get("/api/jobs")
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
        failure_events = [e for e in events if e["outcome"] == "failure"]
        assert len(failure_events) >= 1

    def test_invalid_bearer_token_logs_auth_failure(self, client, _setup_log_dir) -> None:
        """Invalid Bearer token should log an auth failure event."""
        response = client.get(
            "/api/jobs",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 403

        events = _read_audit_log(_setup_log_dir)
        failure_events = [e for e in events if e["outcome"] == "failure"]
        assert len(failure_events) >= 1

    def test_auth_failure_has_details(self, client, _setup_log_dir) -> None:
        """Auth failure events should include method and path details."""
        client.post("/api/jobs", headers={"X-API-Key": "bad"})

        events = _read_audit_log(_setup_log_dir)
        failures = [e for e in events if e["outcome"] == "failure"]
        assert len(failures) >= 1
        details = failures[0].get("details", {})
        assert "method" in details
        assert details.get("has_bearer") is not None

    def test_multiple_failures_all_logged(self, client, _setup_log_dir) -> None:
        """Multiple consecutive auth failures should each be logged."""
        for _ in range(3):
            client.get("/api/jobs", headers={"X-API-Key": "bad"})

        events = _read_audit_log(_setup_log_dir)
        failures = [e for e in events if e["outcome"] == "failure"]
        assert len(failures) >= 3


# ── Auth Success Tests ───────────────────────────────────────────────────


class TestAuthSuccessLogging:
    def test_get_request_does_not_log_success(self, client, _setup_log_dir) -> None:
        """GET requests with valid key should NOT log success (noise reduction)."""
        response = client.get("/api/jobs", headers={"X-API-Key": "test_user_key"})
        assert response.status_code == 200

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
        assert len(success_events) == 0

    def test_post_request_logs_auth_success(self, client, _setup_log_dir) -> None:
        """POST requests with valid key should log auth success."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-API-Key": "test_operator_key"},
        )
        # May get 422 (validation) but should NOT get 403 (auth)
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
        assert len(success_events) >= 1
        assert success_events[0]["event_type"] == "auth"

    def test_admin_key_logs_correct_role(self, client, _setup_log_dir) -> None:
        """Admin key used in POST should log 'admin' role."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-Admin-Key": "test_admin_key"},
        )
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
        assert len(success_events) >= 1
        role = success_events[0].get("details", {}).get("role")
        assert role == "admin", f"Expected admin role, got {role}"

    def test_operator_key_logs_correct_role(self, client, _setup_log_dir) -> None:
        """Operator key used in POST should log 'operator' role."""
        response = client.post(
            "/api/discover",
            json={"url": "https://example.com"},
            headers={"X-API-Key": "test_operator_key"},
        )
        assert response.status_code != 403

        events = _read_audit_log(_setup_log_dir)
        success_events = [e for e in events if e["outcome"] == "success"]
        # Filter for operator role events
        operator_events = [e for e in success_events if e.get("details", {}).get("role") == "operator"]
        assert len(operator_events) >= 1


# ── Public Route Tests ───────────────────────────────────────────────────


class TestPublicRouteDoesNotLog:
    def test_public_route_no_auth_no_log(self, client, _setup_log_dir) -> None:
        """Public routes (outside /api/) should not trigger audit logging."""
        response = client.get("/health")
        assert response.status_code == 200

        events = _read_audit_log(_setup_log_dir)
        assert len(events) == 0, f"Expected no audit events for public routes, got {len(events)}"

    def test_public_route_with_key_no_extra_log(self, client, _setup_log_dir) -> None:
        """Public routes should not log even if a valid key is provided."""
        response = client.get("/health", headers={"X-API-Key": "test_user_key"})
        assert response.status_code == 200

        events = _read_audit_log(_setup_log_dir)
        assert len(events) == 0
