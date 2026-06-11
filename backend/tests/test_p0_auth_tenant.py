"""P0 auth and tenant-isolation regression tests."""

from __future__ import annotations

import pytest
from app.config import settings
from app.models import Job, JobStatus, LogEntry, ScrapeMode
from app.utils.rbac import _fingerprint_key


def _configure_keys(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str = "user-key",
    operator_key: str = "operator-key",
    admin_key: str = "admin-key",
    env: str = "test",
    allow_dev_auth: bool = False,
) -> None:
    monkeypatch.setattr(settings, "API_KEY", api_key)
    monkeypatch.setattr(settings, "OPERATOR_API_KEY", operator_key)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", admin_key)
    monkeypatch.setattr(settings, "ENV", env)
    monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", allow_dev_auth)


def _seed_job(
    job_id: str,
    *,
    owner_key: str,
    in_recycle_bin: bool = False,
) -> Job:
    import app.main as main_mod

    job = Job(
        id=job_id,
        name=f"Tenant job {job_id}",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com/data"],
        status=JobStatus.COMPLETED,
        created_by=_fingerprint_key(owner_key),
        results=[{"company": "Acme", "source_url": "https://example.com/data"}],
        logs=[LogEntry(message="completed", level="info")],
    )
    if in_recycle_bin:
        main_mod.recycle_bin_store[job.id] = job
    else:
        main_mod.jobs_store[job.id] = job
    return job


def test_operator_session_cookie_reaches_rbac_system_status(client, monkeypatch) -> None:
    _configure_keys(monkeypatch)

    login = client.post("/api/session", headers={"X-API-Key": "operator-key"})
    assert login.status_code == 200
    cookie = login.cookies.get("dataforge_session")
    assert cookie

    response = client.get("/api/system/status", cookies={"dataforge_session": cookie})

    assert response.status_code == 200


def test_operator_session_cookie_reaches_storage_status(client, monkeypatch) -> None:
    _configure_keys(monkeypatch)

    login = client.post("/api/session", headers={"X-API-Key": "operator-key"})
    assert login.status_code == 200
    cookie = login.cookies.get("dataforge_session")
    assert cookie

    response = client.get("/api/system/storage/status", cookies={"dataforge_session": cookie})

    assert response.status_code == 200


def test_user_session_cookie_cannot_access_operator_endpoint(client, monkeypatch) -> None:
    _configure_keys(monkeypatch)

    login = client.post("/api/session", headers={"X-API-Key": "user-key"})
    assert login.status_code == 200
    cookie = login.cookies.get("dataforge_session")
    assert cookie

    response = client.get("/api/system/status", cookies={"dataforge_session": cookie})

    assert response.status_code == 403


def test_malformed_session_cookie_is_rejected_on_protected_route(client, monkeypatch) -> None:
    _configure_keys(monkeypatch)

    response = client.get("/api/system/status", cookies={"dataforge_session": "not-a-valid-cookie"})

    assert response.status_code == 403


def test_expired_session_cookie_is_rejected_on_protected_route(client, monkeypatch) -> None:
    import app.auth.session as session_mod
    from app.auth.session import create_session_cookie

    _configure_keys(monkeypatch)
    monkeypatch.setattr(session_mod, "SESSION_MAX_AGE", -1)
    cookie = create_session_cookie("operator")

    response = client.get("/api/system/status", cookies={"dataforge_session": cookie})

    assert response.status_code == 403


def test_api_key_and_bearer_auth_still_reach_system_status(client, monkeypatch) -> None:
    _configure_keys(monkeypatch)

    api_key_response = client.get("/api/system/status", headers={"X-API-Key": "operator-key"})
    bearer_response = client.get("/api/system/status", headers={"Authorization": "Bearer operator-key"})

    assert api_key_response.status_code == 200
    assert bearer_response.status_code == 200


@pytest.mark.parametrize("path", ["/api/jobs", "/api/recycle_bin", "/api/system/status"])
def test_api_routes_fail_closed_without_configured_keys(client, monkeypatch, path: str) -> None:
    _configure_keys(monkeypatch, api_key="", operator_key="", admin_key="", env="test", allow_dev_auth=False)

    response = client.get(path)

    assert response.status_code == 403


def test_explicit_test_dev_auth_allows_protected_route_without_keys(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="", operator_key="", admin_key="", env="test", allow_dev_auth=True)

    response = client.get("/api/system/status")

    assert response.status_code == 200


def test_session_me_remains_public_without_configured_keys(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="", operator_key="", admin_key="", env="test", allow_dev_auth=False)

    response = client.get("/api/session/me")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_user_cannot_list_another_users_jobs(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="user-b-key")
    _seed_job("tenant-job-a", owner_key="user-a-key")

    response = client.get("/api/jobs", headers={"X-API-Key": "user-b-key"})

    assert response.status_code == 200
    ids = {job["id"] for job in response.json()["jobs"]}
    assert "tenant-job-a" not in ids


@pytest.mark.parametrize(
    "path",
    [
        "/api/jobs/tenant-job-a",
        "/api/jobs/tenant-job-a/results",
        "/api/jobs/tenant-job-a/events",
    ],
)
def test_user_cannot_read_another_users_job_detail_results_or_events(client, monkeypatch, path: str) -> None:
    _configure_keys(monkeypatch, api_key="user-b-key")
    _seed_job("tenant-job-a", owner_key="user-a-key")

    response = client.get(path, headers={"X-API-Key": "user-b-key"})

    assert response.status_code in {403, 404}


def test_user_cannot_list_another_users_recycle_bin_items(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="user-b-key")
    _seed_job("tenant-recycled-a", owner_key="user-a-key", in_recycle_bin=True)

    response = client.get("/api/recycle_bin", headers={"X-API-Key": "user-b-key"})

    assert response.status_code == 200
    ids = {job["id"] for job in response.json()["jobs"]}
    assert "tenant-recycled-a" not in ids


def test_admin_can_read_user_job(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="user-b-key", admin_key="admin-key")
    _seed_job("tenant-job-a", owner_key="user-a-key")

    response = client.get("/api/jobs/tenant-job-a", headers={"X-API-Key": "admin-key"})

    assert response.status_code == 200
    assert response.json()["id"] == "tenant-job-a"


def test_operator_policy_allows_operational_job_listing(client, monkeypatch) -> None:
    _configure_keys(monkeypatch, api_key="user-b-key", operator_key="operator-key")
    _seed_job("tenant-job-a", owner_key="user-a-key")

    response = client.get("/api/jobs", headers={"X-API-Key": "operator-key"})

    assert response.status_code == 200
    ids = {job["id"] for job in response.json()["jobs"]}
    assert "tenant-job-a" in ids


def test_denied_cross_tenant_job_read_is_audit_logged(client, monkeypatch) -> None:
    from app.routers import jobs_read

    _configure_keys(monkeypatch, api_key="user-b-key")
    _seed_job("tenant-job-a", owner_key="user-a-key")
    events: list[dict] = []

    def capture_event(**kwargs) -> None:
        events.append(kwargs)

    monkeypatch.setattr(jobs_read, "log_rbac_event", capture_event, raising=False)

    response = client.get("/api/jobs/tenant-job-a", headers={"X-API-Key": "user-b-key"})

    assert response.status_code in {403, 404}
    assert events
    assert events[0]["outcome"] == "denied"
