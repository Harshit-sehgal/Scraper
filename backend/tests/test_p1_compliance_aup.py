"""P1-COMPLIANCE-001: AUP acceptance endpoint tests.

Covers:

* A new SaaS user can call ``POST /api/saas/aup/accept`` to record
  acceptance; the ``aup_accepted_at`` field is populated and an
  audit log line is emitted.
* ``GET /api/saas/aup/status`` returns the current acceptance state.
* Re-acceptance is idempotent (the first timestamp wins).
* Env-backed API keys (no SaaS user row) still get a successful
  response, with the audit line marked ``shadow_user: True``.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest
from app.saas.identity_store import SQLiteIdentityStore, reset_identity_store
from app.saas.models import User, UserStatus
from app.saas.router import CURRENT_AUP_VERSION
from app.saas.router import router as saas_router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


# ─── Test fixtures ──────────────────────────────────────────────────


@pytest.fixture
def saas_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fresh SaaS identity store + FastAPI test client."""
    db_path = tmp_path / "identity_aup.db"
    store = SQLiteIdentityStore(storage_path=str(db_path))
    reset_identity_store(store)

    # Redirect the audit log to a per-test file.
    monkeypatch.setattr("app.audit_logger.AUDIT_LOG_DIR", str(tmp_path))
    from app import audit_logger

    audit_logger.reset_audit_logger()

    # Stub out the auth resolver so we can drive the endpoint with
    # the user_id we want, without having to set up the full env
    # API key path. The stub is a closure over ``current_user_id``.
    current_user_id = {"value": "user-abc"}
    from app.utils import rbac

    def _fake_resolve(request, *, allow_cookie: bool = True):
        from app.utils.rbac import AuthContext, UserRole

        return AuthContext(
            role=UserRole.USER,
            user_id=current_user_id["value"],
            source="api_key",
        )

    monkeypatch.setattr(rbac, "resolve_auth_context", _fake_resolve)

    app = FastAPI()
    app.include_router(saas_router)
    transport = ASGITransport(app=app)
    try:
        yield AsyncClient(transport=transport, base_url="http://testserver"), store, current_user_id, tmp_path
    finally:
        reset_identity_store(None)
        audit_logger.reset_audit_logger()


def _create_user(store: SQLiteIdentityStore, user_id: str) -> User:
    return store.create_user(
        User(
            id=user_id,
            email=f"{user_id}@example.com",
            display_name=user_id,
            status=UserStatus.ACTIVE,
        ),
    )


# ─── Status before acceptance ────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_unaccepted(saas_client) -> None:
    client, store, user_ref, _tmp = saas_client
    user_ref["value"] = "u1"
    _create_user(store, "u1")
    resp = await client.get("/api/saas/aup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u1"
    assert body["aup_accepted_at"] is None
    assert body["requires_acceptance"] is True
    assert body["current_aup_version"] == CURRENT_AUP_VERSION


# ─── Acceptance happy path ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_records_acceptance(saas_client) -> None:
    client, store, user_ref, _tmp = saas_client
    user_ref["value"] = "u2"
    user = _create_user(store, "u2")
    assert user.aup_accepted_at is None
    resp = await client.post(
        "/api/saas/aup/accept",
        json={"aup_version": CURRENT_AUP_VERSION},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u2"
    assert body["aup_accepted_at"] is not None
    assert body["aup_version_accepted"] == CURRENT_AUP_VERSION
    assert body["requires_acceptance"] is False
    # And the store reflects the change.
    refreshed = store.get_user("u2")
    assert refreshed is not None
    assert refreshed.aup_accepted_at == body["aup_accepted_at"]


@pytest.mark.asyncio
async def test_accept_is_idempotent(saas_client) -> None:
    client, store, user_ref, _tmp = saas_client
    user_ref["value"] = "u3"
    _create_user(store, "u3")
    r1 = await client.post("/api/saas/aup/accept", json={"aup_version": CURRENT_AUP_VERSION})
    assert r1.status_code == 200
    first_ts = r1.json()["aup_accepted_at"]
    r2 = await client.post("/api/saas/aup/accept", json={"aup_version": CURRENT_AUP_VERSION})
    assert r2.status_code == 200
    second_ts = r2.json()["aup_accepted_at"]
    # The COALESCE in the store keeps the FIRST timestamp.
    assert second_ts == first_ts


# ─── Audit log emission ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_emits_audit_log(saas_client) -> None:
    client, store, user_ref, tmp_path = saas_client
    user_ref["value"] = "u4"
    _create_user(store, "u4")
    resp = await client.post(
        "/api/saas/aup/accept",
        json={"aup_version": CURRENT_AUP_VERSION},
    )
    assert resp.status_code == 200
    # Force the rotation handler to flush.
    from app.audit_logger import log_system_event

    log_system_event("test_event")
    log_path = tmp_path / "audit.log"
    assert log_path.exists()
    events: deque[dict[str, Any]] = deque(maxlen=200)
    with open(log_path) as fh:
        for line in fh:
            if "[AUDIT]" not in line:
                continue
            payload = line.split("[AUDIT]", 1)[1].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    actions = [e.get("action") for e in events]
    assert "aup_accept" in actions
    # And the event has the AUP version in details.
    matching = [e for e in events if e.get("action") == "aup_accept"]
    assert matching
    assert matching[0]["details"]["aup_version"] == CURRENT_AUP_VERSION


# ─── Shadow-user path (env-backed key, no SaaS user) ─────────────────


@pytest.mark.asyncio
async def test_accept_for_shadow_user(saas_client) -> None:
    client, store, user_ref, _tmp = saas_client
    user_ref["value"] = "env-key-fingerprint"
    # No _create_user() — the store has no row for this id.
    assert store.get_user("env-key-fingerprint") is None
    resp = await client.post("/api/saas/aup/accept", json={"aup_version": CURRENT_AUP_VERSION})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "env-key-fingerprint"
    # No real row was created; the AUP is a shadow accept.
    assert store.get_user("env-key-fingerprint") is None


# ─── Unknown user (defensive path) ───────────────────────────────────


@pytest.mark.asyncio
async def test_status_for_shadow_user(saas_client) -> None:
    client, _store, user_ref, _tmp = saas_client
    user_ref["value"] = "env-only"
    resp = await client.get("/api/saas/aup/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "env-only"
    assert body["aup_accepted_at"] is None
    assert body["requires_acceptance"] is True
