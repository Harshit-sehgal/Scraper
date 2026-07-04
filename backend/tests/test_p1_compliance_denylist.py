"""P1-COMPLIANCE-001: admin domain denylist tests.

Covers:

* ``DomainDenylist`` CRUD (add, remove, list, is_blocked) against a
  per-test SQLite file
* ``validate_against_denylist`` raises on blocked URLs and is silent
  on safe URLs
* ``validate_public_http_url`` (the public SSRF safety check)
  consults the denylist and rejects blocked hosts
* The admin endpoints at ``/api/operator/denylist`` enforce
  admin-only writes and operator-or-admin reads
* Successful add / remove emit an audit log line
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from app.admin_denylist import (
    DomainDenylist,
    is_blocked,
    set_denylist,
    validate_against_denylist,
)
from app.url_safety import validate_public_http_url

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


# ─── Pure CRUD against a temp SQLite file ────────────────────────────


@pytest.fixture
def fresh_denylist():
    """Return a per-test :class:`DomainDenylist` pointing at a temp file."""
    fd, path = tempfile.mkstemp(prefix="denylist_", suffix=".sqlite")
    os.close(fd)
    instance = DomainDenylist(db_path=path)
    try:
        yield instance
    finally:
        instance.close()
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def test_add_and_is_blocked(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("blocked.example.com", reason="takedown notice")
    assert fresh_denylist.is_blocked("https://blocked.example.com/path") is not None
    assert fresh_denylist.is_blocked("https://blocked.example.com") is not None
    assert fresh_denylist.is_blocked("https://other.example.com/") is None


def test_add_whole_domain_vs_path_prefix(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("partial.example.com", reason="", path_prefix="/private")
    assert fresh_denylist.is_blocked("https://partial.example.com/private/secret") is not None
    assert fresh_denylist.is_blocked("https://partial.example.com/public") is None


def test_remove_returns_true_then_false(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("removable.example.com")
    assert fresh_denylist.remove("removable.example.com") is True
    assert fresh_denylist.remove("removable.example.com") is False


def test_list_returns_all_entries(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("a.example.com", reason="a")
    fresh_denylist.add("b.example.com", reason="b", path_prefix="/x")
    entries = fresh_denylist.list()
    domains = {e.domain for e in entries}
    assert {"a.example.com", "b.example.com"}.issubset(domains)


def test_add_validates_domain(fresh_denylist: DomainDenylist) -> None:
    with pytest.raises(ValueError):
        fresh_denylist.add("")
    with pytest.raises(ValueError):
        fresh_denylist.add("not a domain!")


def test_is_blocked_returns_none_for_unparseable_url(fresh_denylist: DomainDenylist) -> None:
    assert is_blocked("not a url") is None
    assert is_blocked("") is None


def test_validate_against_denylist_raises_for_blocked(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("evil.example.com", reason="abuse")
    with pytest.raises(ValueError, match="admin denylist"):
        fresh_denylist.validate_url("https://evil.example.com/") if hasattr(fresh_denylist, "validate_url") else None
    # Module-level validate_against_denylist reads the singleton; install
    # the per-test denylist as the singleton for this assertion.
    from app.admin_denylist import set_denylist

    set_denylist(fresh_denylist)
    try:
        with pytest.raises(ValueError, match="admin denylist"):
            validate_against_denylist("https://evil.example.com/")
    finally:
        set_denylist(None)


def test_validate_against_denylist_silent_for_safe(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("evil.example.com", reason="abuse")
    # Must not raise
    validate_against_denylist("https://safe.example.com/")


def test_update_existing_entry_preserves_domain(fresh_denylist: DomainDenylist) -> None:
    fresh_denylist.add("update.example.com", reason="first")
    fresh_denylist.add("update.example.com", reason="second")
    entries = fresh_denylist.list()
    matching = [e for e in entries if e.domain == "update.example.com"]
    assert len(matching) == 1
    assert matching[0].reason == "second"


# ─── URL safety integration ──────────────────────────────────────────


@pytest.fixture
def installed_denylist(fresh_denylist: DomainDenylist):
    """Install *fresh_denylist* as the module singleton for the duration of the test."""
    set_denylist(fresh_denylist)
    try:
        yield fresh_denylist
    finally:
        set_denylist(None)


def test_url_safety_rejects_denylisted_domain(installed_denylist: DomainDenylist) -> None:
    installed_denylist.add("denied.example.com", reason="abuse report")
    with pytest.raises(ValueError, match="admin denylist"):
        validate_public_http_url("https://denied.example.com/article")


def test_url_safety_allows_safe_domain(installed_denylist: DomainDenylist) -> None:
    installed_denylist.add("denied.example.com", reason="abuse report")
    # Should not raise — the URL is safe and not in the denylist.
    validate_public_http_url("https://safe.example.com/article")


# ─── Admin endpoints ──────────────────────────────────────────────────


@pytest.fixture
def denylist_client():
    """A FastAPI test client wired with a fresh denylist + the operator router."""
    from app.routers.operator import router as operator_router
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    fd, path = tempfile.mkstemp(prefix="denylist_admin_", suffix=".sqlite")
    os.close(fd)
    instance = DomainDenylist(db_path=path)
    set_denylist(instance)

    app = FastAPI()
    app.include_router(operator_router)

    # The operator router requires a valid AuthContext.  We mock
    # resolve_auth_context to return ADMIN for ``admin-token`` and
    # OPERATOR for ``operator-token`` so we can exercise both roles.
    from app.utils import rbac

    original_resolve = rbac.resolve_auth_context

    def _fake_resolve(request, *, allow_cookie: bool = True):
        from app.utils.rbac import AuthContext, UserRole

        token = request.headers.get("X-API-Key", "")
        if token == "admin-token":
            return AuthContext(role=UserRole.ADMIN, user_id="admin-fp", source="api_key")
        if token == "operator-token":
            return AuthContext(role=UserRole.OPERATOR, user_id="op-fp", source="api_key")
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="no auth")

    rbac.resolve_auth_context = _fake_resolve

    transport = ASGITransport(app=app)
    try:
        yield AsyncClient(transport=transport, base_url="http://testserver"), instance
    finally:
        rbac.resolve_auth_context = original_resolve
        set_denylist(None)
        instance.close()
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
async def test_list_denylist_returns_entries(denylist_client) -> None:
    client, instance = denylist_client
    instance.add("x.example.com", reason="r1")
    resp = await client.get("/api/operator/denylist", headers={"X-API-Key": "operator-token"})
    assert resp.status_code == 200
    body = resp.json()
    domains = {row["domain"] for row in body}
    assert "x.example.com" in domains


@pytest.mark.asyncio
async def test_admin_can_add_to_denylist(denylist_client) -> None:
    client, instance = denylist_client
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "added.example.com", "reason": "test"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["domain"] == "added.example.com"
    assert body["reason"] == "test"
    # The singleton reflects the change.
    assert is_blocked("https://added.example.com/x") is not None


@pytest.mark.asyncio
async def test_operator_cannot_add_to_denylist(denylist_client) -> None:
    client, _instance = denylist_client
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "operator-blocked.example.com", "reason": "test"},
        headers={"X-API-Key": "operator-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_remove_from_denylist(denylist_client) -> None:
    client, instance = denylist_client
    instance.add("removable.example.com")
    resp = await client.request(
        "DELETE",
        "/api/operator/denylist",
        json={"domain": "removable.example.com"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "removable.example.com"
    assert is_blocked("https://removable.example.com/x") is None


@pytest.mark.asyncio
async def test_admin_remove_missing_returns_404(denylist_client) -> None:
    client, _instance = denylist_client
    resp = await client.request(
        "DELETE",
        "/api/operator/denylist",
        json={"domain": "never-existed.example.com"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_cannot_list_denylist(denylist_client) -> None:
    client, _instance = denylist_client
    resp = await client.get("/api/operator/denylist")
    assert resp.status_code == 403


# ─── Audit log on admin add/remove ───────────────────────────────────


@pytest.mark.asyncio
async def test_admin_add_writes_audit_log(denylist_client, tmp_path, monkeypatch) -> None:
    import json
    from collections import deque

    client, _instance = denylist_client
    audit_log = tmp_path / "audit.log"
    monkeypatch.setattr("app.audit_logger.AUDIT_LOG_DIR", str(tmp_path))
    # Force the audit logger to re-init against the new directory.
    from app import audit_logger

    audit_logger.reset_audit_logger()
    try:
        resp = await client.post(
            "/api/operator/denylist",
            json={"domain": "audited.example.com", "reason": "audit test"},
            headers={"X-API-Key": "admin-token"},
        )
        assert resp.status_code == 201
        # The audit logger writes lazily; the file may not exist yet
        # until the handler flushes.  We trigger a no-op write to make
        # sure the rotation handler has been instantiated.
        from app.audit_logger import log_system_event

        log_system_event("test_event")
        assert audit_log.exists()
        events: deque[dict[str, Any]] = deque(maxlen=200)
        with open(audit_log) as fh:
            for line in fh:
                line = line.strip()
                if "[AUDIT]" in line:
                    payload = line.split("[AUDIT]", 1)[1].strip()
                    try:
                        events.append(json.loads(payload))
                    except json.JSONDecodeError:
                        continue
        actions = {e.get("action") for e in events}
        assert "denylist_add" in actions
    finally:
        audit_logger.reset_audit_logger()


# ─── uncovered error-path branches (operator router) ────────────────


@pytest.mark.asyncio
async def test_admin_add_invalid_domain_returns_400(denylist_client) -> None:
    """Adding a domain that fails DomainDenylist.add validation MUST
    surface as HTTP 400 with the validation message — not a 500 or a
    silent success.  This is the ``ValueError as exc → HTTPException(400)``
    branch in operator.add_denylist_entry that was previously untested."""
    client, _instance = denylist_client
    # Spaces and '*' are not in the allowed [a-z0-9.-] set.
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "has space.invalid", "reason": "bad"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_add_empty_domain_rejected_at_pydantic(denylist_client) -> None:
    """An empty domain (min_length=1) is rejected by pydantic before it
    even reaches the route body — FastAPI returns 422, not 400."""
    client, _instance = denylist_client
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "", "reason": "empty"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_add_path_prefix_without_slash_returns_400(denylist_client) -> None:
    """A path_prefix that does not start with '/' trips the ValueError
    in DomainDenylist.add → 400 (the third validation branch)."""
    client, _instance = denylist_client
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "pfx.example.com", "reason": "r", "path_prefix": "no-slash"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 400
    assert "path_prefix" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_add_with_path_prefix_scopes_block(denylist_client) -> None:
    """A path_prefix-scoped entry blocks only that path, leaving the
    rest of the domain accessible. Verifies the persisted row round-trips
    its path_prefix in the response and is_blocked honours the scope."""
    client, instance = denylist_client
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "scoped.example.com", "reason": "r", "path_prefix": "/private"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["path_prefix"] == "/private"

    # The /private prefix is blocked; the bare domain and another path are not.
    assert is_blocked("https://scoped.example.com/private/secret") is not None
    assert is_blocked("https://scoped.example.com/public") is None
    assert is_blocked("https://scoped.example.com/") is None


@pytest.mark.asyncio
async def test_admin_remove_with_path_prefix_returns_200(denylist_client) -> None:
    """Removing a path_prefix-scoped entry removes only that entry —
    the bare-domain entry (if any) is unaffected.  Verifies the
    remove endpoint round-trips the path_prefix in its response."""
    client, instance = denylist_client
    # Add the scoped entry directly so we control its existence.
    instance.add("scoped-rm.example.com", path_prefix="/admin")
    assert is_blocked("https://scoped-rm.example.com/admin/x") is not None

    resp = await client.request(
        "DELETE",
        "/api/operator/denylist",
        json={"domain": "scoped-rm.example.com", "path_prefix": "/admin"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["path_prefix"] == "/admin"
    # The scoped block is gone.
    assert is_blocked("https://scoped-rm.example.com/admin/x") is None


@pytest.mark.asyncio
async def test_admin_remove_wrong_path_prefix_returns_404(denylist_client) -> None:
    """If a domain has an entry but with a different path_prefix, the
    remove with a non-matching prefix MUST 404 — the entry the
    operator described does not exist."""
    client, instance = denylist_client
    instance.add("wrongpfx.example.com", path_prefix="/admin")
    resp = await client.request(
        "DELETE",
        "/api/operator/denylist",
        json={"domain": "wrongpfx.example.com", "path_prefix": "/other"},
        headers={"X-API-Key": "admin-token"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_operator_can_list_but_not_write(denylist_client) -> None:
    """Operator role may GET /denylist but post/DELETE yield 403 —
    the require_role_with_user([UserRole.ADMIN]) dependency rejects."""
    client, instance = denylist_client
    instance.add("op-list.example.com", reason="r")

    # GET works.
    resp = await client.get("/api/operator/denylist", headers={"X-API-Key": "operator-token"})
    assert resp.status_code == 200
    domains = {row["domain"] for row in resp.json()}
    assert "op-list.example.com" in domains

    # POST forbidden.
    resp = await client.post(
        "/api/operator/denylist",
        json={"domain": "op-add.example.com"},
        headers={"X-API-Key": "operator-token"},
    )
    assert resp.status_code == 403

    # DELETE forbidden.
    resp = await client.request(
        "DELETE",
        "/api/operator/denylist",
        json={"domain": "op-list.example.com"},
        headers={"X-API-Key": "operator-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_remove_writes_audit_log_with_path_prefix_resource(
    denylist_client,
    tmp_path,
    monkeypatch,
) -> None:
    """The audit log resource string for a scoped remove MUST carry the
    path_prefix (e.g. ``domain:foo.example.com:/admin``) — operators
    need the scope on the audit trail to explain why a scoped block
    was lifted."""
    import json
    from collections import deque

    client, _instance = denylist_client
    audit_log = tmp_path / "audit.log"
    monkeypatch.setattr("app.audit_logger.AUDIT_LOG_DIR", str(tmp_path))
    from app import audit_logger

    audit_logger.reset_audit_logger()
    try:
        # Add a scoped entry to remove.
        add_resp = await client.post(
            "/api/operator/denylist",
            json={"domain": "audit-rm.example.com", "path_prefix": "/admin"},
            headers={"X-API-Key": "admin-token"},
        )
        assert add_resp.status_code == 201
        # Now remove it.
        resp = await client.request(
            "DELETE",
            "/api/operator/denylist",
            json={"domain": "audit-rm.example.com", "path_prefix": "/admin"},
            headers={"X-API-Key": "admin-token"},
        )
        assert resp.status_code == 200

        from app.audit_logger import log_system_event

        log_system_event("test_event")
        assert audit_log.exists()
        events: deque[dict[str, Any]] = deque(maxlen=200)
        with open(audit_log) as fh:
            for line in fh:
                line = line.strip()
                if "[AUDIT]" in line:
                    payload = line.split("[AUDIT]", 1)[1].strip()
                    try:
                        events.append(json.loads(payload))
                    except json.JSONDecodeError:
                        continue
        # An audit entry for denylist_remove of the scoped domain exists,
        # and its resource string embeds the path_prefix.
        remove_events = [e for e in events if e.get("action") == "denylist_remove"]
        assert remove_events, "expected a denylist_remove audit entry"
        assert any("/admin" in (e.get("resource", "") or "") for e in remove_events)
    finally:
        audit_logger.reset_audit_logger()
