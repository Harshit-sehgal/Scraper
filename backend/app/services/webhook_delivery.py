"""Webhook delivery service — POST job-completion callbacks with retry and HMAC signing.

When a job reaches a terminal state (COMPLETED, FAILED, DEGRADED,
EMPTY_RESULT, CANCELED) and has a ``webhook_url`` configured, this
service delivers a JSON payload via HTTP POST. If the first attempt
fails, it retries with exponential backoff up to ``MAX_RETRIES``
times.

Payload signing
---------------
If the job has a ``webhook_secret``, the payload is HMAC-SHA256 signed
and the signature is included in an ``X-DataForge-Signature`` header.
Consumers verify by computing the HMAC of the raw body with the same
secret and comparing (preferably using ``hmac.compare_digest``).

Security
--------
- Only ``https://`` and ``http://`` URLs are allowed (validated at
  model level).
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
_BACKOFF_MULTIPLIER: float = 2.0
_WEBHOOK_TIMEOUT_SECONDS: float = 10.0


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


async def deliver_webhook(job: Any) -> bool:
    """Deliver a job-completion webhook with retries.

    Returns ``True`` if delivery succeeded, ``False`` otherwise.
    Updates ``job.webhook_delivered`` and ``job.webhook_delivered_at``
    on success.
    """
    webhook_url = getattr(job, "webhook_url", None)
    if not webhook_url:
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

    import httpx

    backoff = _INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(webhook_url, content=payload_bytes, headers=headers)
                if resp.status_code < 400:
                    job.webhook_delivered = True
                    job.webhook_delivered_at = datetime.datetime.now(datetime.UTC).isoformat()
                    logger.info(
                        "Webhook delivered for job %s to %s (HTTP %d, attempt %d)",
                        getattr(job, "id", ""),
                        webhook_url,
                        resp.status_code,
                        attempt,
                    )
                    return True

                logger.warning(
                    "Webhook delivery failed for job %s (HTTP %d, attempt %d/%d)",
                    getattr(job, "id", ""),
                    resp.status_code,
                    attempt,
                    MAX_RETRIES,
                )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
            logger.warning(
                "Webhook delivery error for job %s (attempt %d/%d): %s",
                getattr(job, "id", ""),
                attempt,
                MAX_RETRIES,
                exc,
            )

        if attempt < MAX_RETRIES:
            import asyncio

            await asyncio.sleep(backoff)
            backoff *= _BACKOFF_MULTIPLIER

    logger.error(
        "Webhook delivery exhausted retries for job %s → %s",
        getattr(job, "id", ""),
        webhook_url,
    )
    return False
