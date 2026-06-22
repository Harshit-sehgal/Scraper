"""Session-based authentication for DataForge SaaS.

Stateless session management using HMAC-signed cookies.
Exchanges a valid API key for an HTTP-only session cookie,
removing the need for the browser to hold the raw API key in memory.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request, Response

SESSION_COOKIE = "dataforge_session"
SESSION_MAX_AGE = 86400  # 24 hours


def _session_db_path() -> Path:
    """Resolve the server-side session registry path."""
    identity_path = getattr(settings, "IDENTITY_DB_PATH", "")
    if identity_path:
        path = Path(identity_path).expanduser().with_name("session.db")
    else:
        from app.job_store import _get_db_path

        path = _get_db_path().with_name("session.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect_session_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_session_db_path()), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_session_schema() -> None:
    with _connect_session_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                sid TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER DEFAULT NULL
            )
            """,
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at)")
        conn.commit()


def _create_server_session(role: str, user_id: str, *, issued_at: int, max_age: int) -> str:
    """Persist a revocable server-side session and return its opaque ID."""
    sid = str(uuid.uuid4())
    try:
        _ensure_session_schema()
        with _connect_session_db() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (sid, role, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sid, role, user_id or "", issued_at, issued_at + max_age),
            )
            conn.commit()
    except (OSError, sqlite3.Error):
        # Fail closed: an unregistered session id will not verify.
        return ""
    return sid


def _server_session_is_active(sid: str, role: str, user_id: str, *, now: int) -> bool:
    """Return True only for a known, unrevoked, unexpired session."""
    if not sid:
        return False
    try:
        _ensure_session_schema()
        with _connect_session_db() as conn:
            row = conn.execute(
                """
                SELECT role, user_id, expires_at, revoked_at
                FROM auth_sessions
                WHERE sid = ?
                """,
                (sid,),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return False
    if row is None:
        return False
    return (
        str(row["role"]) == role
        and str(row["user_id"] or "") == (user_id or "")
        and row["revoked_at"] is None
        and int(row["expires_at"]) >= now
    )


def revoke_session_cookie(cookie_value: str) -> bool:
    """Revoke the server-side session referenced by a signed cookie."""
    payload = _unsign(cookie_value)
    if payload is None:
        return False
    try:
        raw = base64.urlsafe_b64decode(payload + "==")
        data = json.loads(raw.decode("utf-8"))
        sid = str(data.get("sid", ""))
    except (TypeError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return False
    if not sid:
        return False
    try:
        _ensure_session_schema()
        with _connect_session_db() as conn:
            cursor = conn.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE sid = ? AND revoked_at IS NULL",
                (int(time.time()), sid),
            )
            conn.commit()
            return cursor.rowcount > 0
    except (OSError, sqlite3.Error):
        return False


def _derive_secret() -> bytes:
    """Derive a deterministic signing key from the configured secret or a default.

    In production, operators MUST set ``DATAFORGE_SESSION_SECRET`` to a
    unique, unpredictable value. The fallback is derived from the admin
    API key so that two deployments with different admin keys get different
    signing keys. If both are unset, a random per-boot key is generated
    (sessions invalidate on restart).
    """
    raw = settings.SESSION_SECRET or settings.ADMIN_API_KEY
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).digest()
    return hashlib.sha256(os.urandom(32)).digest()


_SIGNING_KEY = _derive_secret()


def _sign(payload: str) -> str:
    """Return an HMAC-SHA256 signature (hex-encoded) for *payload*."""
    return hmac.new(_SIGNING_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _unsign(signed: str) -> str | None:
    """Verify and return the payload from a signed cookie value, or None on failure.

    H11: Try primary key, then rotated keys for secret rotation support.
    """
    try:
        payload, sig = signed.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None

    # Try primary key
    expected = _sign(payload)
    if hmac.compare_digest(sig, expected):
        return payload

    # H11: Try rotated keys
    try:
        import os

        rotated = os.environ.get("DATAFORGE_SESSION_SECRET_ROTATED", "").strip()
        if rotated:
            for old_secret in rotated.split(";"):
                if not old_secret.strip():
                    continue
                old_key = hashlib.sha256(old_secret.strip().encode()).digest()[:32]
                expected_old = hmac.new(old_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected_old):
                    return payload
    except (ValueError, TypeError, UnicodeError):
        return None

    return None


def create_session_cookie(role: str, user_id: str = "") -> str:
    """Create a signed session cookie value embedding role and identity."""
    issued_at = int(time.time())
    max_age = SESSION_MAX_AGE
    sid = _create_server_session(role, user_id, issued_at=issued_at, max_age=max_age)
    if not sid:
        msg = "failed to create server-side session"
        raise RuntimeError(msg)
    data = json.dumps(
        {"role": role, "user_id": user_id, "iat": issued_at, "max_age": max_age, "sid": sid},
        separators=(",", ":"),
    )
    payload = base64.urlsafe_b64encode(data.encode("utf-8")).decode("ascii").rstrip("=")
    sig = _sign(payload)
    return f"{payload}.{sig}"


def verify_session_payload(cookie_value: str) -> dict[str, object] | None:
    """Verify a signed session cookie and return its payload, or None.

    Also rejects expired sessions.
    """
    payload = _unsign(cookie_value)
    if payload is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(payload + "==")  # padding may have been stripped
        data = json.loads(raw.decode("utf-8"))
        iat = int(data.get("iat", 0))
        max_age = int(data.get("max_age", SESSION_MAX_AGE))
    except (TypeError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None

    role = str(data.get("role", ""))
    user_id = str(data.get("user_id", ""))
    sid = str(data.get("sid", ""))

    now = int(time.time())
    if role not in {"admin", "operator", "user"} or max_age < 0 or now > iat + max_age:
        return None
    if not _server_session_is_active(sid, role, user_id, now=now):
        return None
    return {"role": role, "user_id": user_id, "iat": iat, "max_age": max_age, "sid": sid}


def verify_session_cookie(cookie_value: str) -> str | None:
    """Verify a signed session cookie and return the embedded role, or None."""
    payload = verify_session_payload(cookie_value)
    if payload is None:
        return None
    return str(payload["role"])


def _session_cookie_secure() -> bool:
    """Require HTTPS-only session cookies in production-like environments."""
    return (settings.ENV or "").strip().lower() in {"production", "staging"}


def set_session_cookie(response: Response, role: str, user_id: str = "") -> None:
    """Set the session cookie on *response* for the authenticated principal."""
    cookie_value = create_session_cookie(role, user_id=user_id)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=cookie_value,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=_session_cookie_secure(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie on *response*."""
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=_session_cookie_secure(),
    )


def get_session_role(request: Request) -> str | None:
    """Extract the authenticated role from the session cookie, if valid."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    return verify_session_cookie(cookie)


def get_session_payload(request: Request) -> dict[str, object] | None:
    """Extract the verified session payload from the cookie, if present."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    return verify_session_payload(cookie)
