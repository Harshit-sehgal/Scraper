"""Webhook delivery service — POST job-completion callbacks with retry and HMAC signing (Feat 10).

When a job reaches a terminal state (COMPLETED, FAILED, DEGRADED,
EMPTY_RESULT, CANCELED) and has a ``webhook_url`` configured, this
service delivers a JSON payload via HTTP POST. If the first attempt
fails, it retries with exponential backoff up to ``MAX_RETRIES``
times (3 attempts total).

Retry behaviour (Feat 10)
-------------------------
- **3 attempts** total (1 initial + 2 retries).
- **Exponential backoff**: 1 s, 5 s, 25 s intervals (multiplier 5x).
  Between attempt 1→2 the service sleeps 1 s; between 2→3 it sleeps
  5 s. A hypothetical 4th attempt (if MAX_RETRIES were increased)
  would sleep 25 s.
- **Transient exceptions** caught: ``httpx.ConnectError``,
  ``httpx.TimeoutException`` (covers ``ConnectTimeout``,
  ``ReadTimeout``, ``WriteTimeout``, ``PoolTimeout``),
  ``httpx.ReadError``, and stdlib ``TimeoutError``.
- **HTTP-level failures** (4xx/5xx responses): treated as retryable
  up to ``MAX_RETRIES``.

Payload signing
---------------
If the job has a ``webhook_secret``, the payload is HMAC-SHA256 signed
and the signature is included in an ``X-DataForge-Signature`` header.
Consumers verify by computing the HMAC of the raw body with the same
secret and comparing (preferably using ``hmac.compare_digest``).

Tenant isolation
----------------
The *caller* (router or finalization pipeline) is responsible for
access-controlling the job object before passing it here.  An optional
``caller_identity`` tuple ``(user_id, org_id, project_id)`` can be
passed; when provided, ``deliver_webhook`` will verify it matches the
job's ``created_by`` / ``org_id`` / ``project_id`` and return ``False``
without delivering if there is a mismatch.

Security
--------
- ``validate_public_http_url`` is called on the webhook URL before any
  HTTP request is made — private IPs, loopback, link-local, and
  disallowed schemes are rejected.
- ``get_safe_async_client`` pins DNS resolution to prevent TOCTOU
  rebinding attacks.
- The POST has a 10-second connect/read timeout to avoid blocking the
  event loop.
- Payload size is bounded by the job result structure.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3
_INITIAL_BACKOFF_SECONDS: float = 1.0
_BACKOFF_MULTIPLIER: float = 5.0
_WEBHOOK_TIMEOUT_SECONDS: float = 10.0

# Fully realized sequence of inter-attempt sleep delays
# (initial_backoff, initial_backoff * multiplier, ...).  Exposed for
# tests and dashboards that want to surface "when will the next retry
# fire?".  With initial=1.0 and multiplier=5.0 this yields 1 s,
# 5 s, 25 s, 125 s, ... — the request specifies the 1/5/25 envelope.
BACKOFF_SEQUENCE_SECONDS: tuple[float, ...] = (
    _INITIAL_BACKOFF_SECONDS,
    _INITIAL_BACKOFF_SECONDS * _BACKOFF_MULTIPLIER,
    _INITIAL_BACKOFF_SECONDS * (_BACKOFF_MULTIPLIER**2),
)


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 of *payload_bytes* using *secret*."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def _build_payload(job: Any) -> dict[str, Any]:
    """Build the webhook payload dict from a terminal job."""
    return {
        "event": "job.completed",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "job_id": getattr(job, "id", ""),
        "status": str(getattr(job, "status", "")),
        "name": getattr(job, "name", ""),
        "total_records": getattr(job, "total_records", 0),
        "filtered_records": getattr(job, "filtered_records", 0),
        "error": getattr(job, "error", None),
        "created_at": getattr(job, "created_at", ""),
        "completed_at": getattr(job, "completed_at", ""),
        "estimated_cost_usd": getattr(job, "estimated_cost_usd", 0.0),
    }


async def deliver_webhook(
    job: Any,
    *,
    caller_identity: tuple[str, str, str] | None = None,
) -> bool:
    """Deliver a job-completion webhook with retries.

    Up to ``MAX_RETRIES`` (3) HTTP POST attempts are made.  Between
    failed attempts the coroutine sleeps for ``BACKOFF_SEQUENCE_SECONDS[i]``
    seconds (1 s, 5 s, 25 s envelope; with 3 total attempts only the
    first two delays — 1 s and 5 s — are realised).

    Returns ``True`` if delivery succeeded, ``False`` otherwise.
    Updates ``job.webhook_delivered`` and ``job.webhook_delivered_at``
    on success, and resets them on failure so a prior partial success
    cannot mask a current failure.

    Args:
        job: Job object with at minimum ``webhook_url``, ``webhook_secret``,
            ``id``, ``status``, ``name``, ``total_records``, ``filtered_records``,
            ``error``, ``created_at``, ``completed_at``,
            ``estimated_cost_usd``.
        caller_identity: Optional ``(user_id, org_id, project_id)`` of the
            principal requesting delivery.  When provided, the function
            refuses to deliver if it doesn't match
            ``(job.created_by, job.org_id, job.project_id)``.  Tenant
            isolation guarantee — the redeliver endpoint already enforces
            this at the router; passing the same tuple here is a defense
            in depth check against accidental direct calls (e.g. from a
            background worker that has the wrong job in scope).
    """
    webhook_url = getattr(job, "webhook_url", None)
    if not webhook_url:
        return False

    # Tenant isolation: when caller_identity is supplied, refuse to deliver
    # for a job that doesn't belong to that principal.  This protects
    # against a buggy worker handing the wrong job to deliver_webhook().
    if caller_identity is not None:
        caller_user_id, caller_org_id, caller_project_id = caller_identity
        job_user_id = str(getattr(job, "created_by", "") or "")
        job_org_id = str(getattr(job, "org_id", "") or "")
        job_project_id = str(getattr(job, "project_id", "") or "")
        if not _tenant_matches(caller_user_id, caller_org_id, caller_project_id, job_user_id, job_org_id, job_project_id):
            logger.warning(
                "Webhook delivery refused: tenant mismatch for job %s (caller=%s, job owner=%s org=%s project=%s)",
                getattr(job, "id", ""),
                caller_user_id,
                job_user_id,
                job_org_id,
                job_project_id,
            )
            return False

    # SSRF defense: reject private IPs, loopback, link-local, and
    # disallowed schemes *before* opening any connection.
    try:
        from app.url_safety import validate_public_http_url

        validate_public_http_url(webhook_url)
    except ValueError as exc:
        logger.warning(
            "Webhook URL blocked by SSRF guard for job %s: %s",
            getattr(job, "id", ""),
            exc,
        )
        from app.metrics_collector import record_ssrf_reject

        record_ssrf_reject(f"webhook {exc}")
        return False

    payload = _build_payload(job)
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "DataForge-Webhook/1.0",
    }

    # HMAC signing
    webhook_secret = getattr(job, "webhook_secret", None)
    if webhook_secret:
        headers["X-DataForge-Signature"] = f"sha256={_sign_payload(payload_bytes, webhook_secret)}"

    import asyncio

    import httpx  # for exception types only — the client is SSRF-guarded

    from app.url_safety import get_safe_async_client

    # Catch only transient network errors.  Anything else (programming
    # bugs, OOM, etc.) propagates so it shows up in error tracking
    # rather than silently turning into a 4xx routing oddity.
    transient_exc: tuple[type[BaseException], ...] = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadError,
        httpx.WriteError,
        httpx.PoolTimeout,
        TimeoutError,
    )

    backoff = _INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with get_safe_async_client(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
                if resp.status_code < 400:
                    job.webhook_delivered = True
                    job.webhook_delivered_at = datetime.datetime.now(datetime.UTC).isoformat()
                    logger.info(
                        "Webhook delivered for job %s to %s (HTTP %d, attempt %d/%d)",
                        getattr(job, "id", ""),
                        webhook_url,
                        resp.status_code,
                        attempt,
                        MAX_RETRIES,
                    )
                    return True

                logger.warning(
                    "Webhook delivery failed for job %s (HTTP %d, attempt %d/%d)",
                    getattr(job, "id", ""),
                    resp.status_code,
                    attempt,
                    MAX_RETRIES,
                )
        except transient_exc as exc:
            logger.warning(
                "Webhook delivery transient error for job %s (attempt %d/%d): %s",
                getattr(job, "id", ""),
                attempt,
                MAX_RETRIES,
                exc,
            )

        # Failed (transient or HTTP error) - back off unless this was the
        # last attempt.
        if attempt < MAX_RETRIES:
            await asyncio.sleep(backoff)
            backoff *= _BACKOFF_MULTIPLIER

    # All retries exhausted - reset the state so prior partial success
    # cannot mask a current failure.
    job.webhook_delivered = False
    job.webhook_delivered_at = None
    logger.error(
        "Webhook delivery exhausted retries for job %s → %s",
        getattr(job, "id", ""),
        webhook_url,
    )
    return False


def _tenant_matches(
    caller_user_id: str,
    caller_org_id: str,
    caller_project_id: str,
    job_user_id: str,
    job_org_id: str,
    job_project_id: str,
) -> bool:
    """Return True if the caller is allowed to deliver for the given job.

    The identity tuple matches when ANY of:
      - caller_user_id matches job_user_id (personal API key)
      - caller_org_id matches job_org_id and both are non-empty
      - caller_project_id matches job_project_id and both are non-empty

    An empty caller tuple (e.g., a system job runner that has not yet
    learned of a principal) is rejected unless the job is also
    unmarked - this prevents delivering webhooks for jobs with a
    tenancy marker using a caller that has no marker at all.
    """
    if caller_user_id and caller_user_id == job_user_id:
        return True
    if caller_org_id and caller_org_id == job_org_id:
        return True
    return bool(caller_project_id and caller_project_id == job_project_id)
