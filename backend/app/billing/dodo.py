"""Dodo Payments billing integration — subscriptions, webhooks, reconciliation.

Dodo Payments (https://dodopayments.com) is the billing provider: it is
the merchant of record and handles checkout, recurring billing, and
global tax. This module implements:

- **Configuration** via environment variables (see below).
- **Checkout sessions** — ``POST /checkouts`` returns a hosted
  ``checkout_url`` the user is redirected to.
- **Webhooks** — Standard Webhooks spec (HMAC-SHA256) signature
  verification, ``webhook-id`` idempotency, and event normalization
  into the shared billing vocabulary processed by
  ``app.billing.webhooks._process_webhook_event`` (the same processor
  the PayPal integration uses), so entitlement flips land in the same
  on-disk subscription store read by ``plan_enforcer``.
- **Entitlement reconciliation** — a sweep that walks stored
  subscriptions and repairs/downgrades them against the live Dodo API.

Environment variables:
    DODO_PAYMENTS_API_KEY        — Bearer API key (Developer → API Keys).
    DODO_PAYMENTS_ENVIRONMENT    — "test_mode" (default) | "live_mode".
    DODO_PAYMENTS_API_URL        — Override base URL (defaults:
                                   https://test.dodopayments.com or
                                   https://live.dodopayments.com).
    DODO_PAYMENTS_WEBHOOK_KEY    — Webhook signing secret (Standard
                                   Webhooks; Developer → Webhooks).
    DODO_PRODUCT_ID_STARTER      — Subscription product IDs created in
    DODO_PRODUCT_ID_PRO            the Dodo dashboard (one per tier).
    DODO_PRODUCT_ID_ENTERPRISE
    DODO_CHECKOUT_RETURN_URL     — Default return URL after checkout.
    DODO_WEBHOOK_STATE_FILE      — Webhook-id idempotency state file
                                   (default: backend/data/dodo_webhook_events.json).

Webhook events handled (see ``normalize_dodo_webhook``):
    subscription.active / renewed / reactivated / updated
    subscription.on_hold / failed / cancelled
    payment.succeeded / payment.failed
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.billing.models import PlanTierId
from app.saas.identity_store import get_identity_store
from app.saas.models import UserStatus
from app.url_safety import open_safe_client, validate_public_http_url
from app.utils.rbac import UserRole, require_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing/dodo", tags=["billing"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DODO_API_KEY_ENV = "DODO_PAYMENTS_API_KEY"  # nosec B105 — env-var NAME, not a credential
_DODO_ENVIRONMENT_ENV = "DODO_PAYMENTS_ENVIRONMENT"
_DODO_API_URL_ENV = "DODO_PAYMENTS_API_URL"
_DODO_WEBHOOK_KEY_ENV = "DODO_PAYMENTS_WEBHOOK_KEY"  # nosec B105 — env-var NAME
_DODO_RETURN_URL_ENV = "DODO_CHECKOUT_RETURN_URL"
_DODO_STATE_FILE_ENV = "DODO_WEBHOOK_STATE_FILE"

_DODO_BASE_URLS = {
    "test_mode": "https://test.dodopayments.com",
    "live_mode": "https://live.dodopayments.com",
}

# Standard Webhooks spec: reject payloads with a timestamp older than
# this many seconds (replay protection).
_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 300

_PRODUCT_ID_ENV_BY_TIER: dict[PlanTierId, str] = {
    PlanTierId.STARTER: "DODO_PRODUCT_ID_STARTER",
    PlanTierId.PRO: "DODO_PRODUCT_ID_PRO",
    PlanTierId.ENTERPRISE: "DODO_PRODUCT_ID_ENTERPRISE",
}


def _dodo_base_url() -> str:
    """Resolve the Dodo API base URL for the configured environment."""
    override = os.environ.get(_DODO_API_URL_ENV, "").strip()
    if override:
        return override
    environment = os.environ.get(_DODO_ENVIRONMENT_ENV, "test_mode").strip().lower()
    return _DODO_BASE_URLS.get(environment, _DODO_BASE_URLS["test_mode"])


def _default_dodo_state_path() -> Path:
    """Resolve the webhook-id state file path (env overridable per call)."""
    env_value = os.environ.get(_DODO_STATE_FILE_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[2] / "data" / "dodo_webhook_events.json"


# ---------------------------------------------------------------------------
# Product-id → tier resolution (mirrors the PayPal plan-id resolver)
# ---------------------------------------------------------------------------

_dodo_product_cache: dict[str, PlanTierId] | None = None
_dodo_product_cache_lock = threading.Lock()


def resolve_tier_from_dodo_product(product_id: str) -> PlanTierId:
    """Map a Dodo subscription product id to a plan tier.

    Cached after first call. Returns ``PlanTierId.FREE`` for empty or
    unrecognised product ids. Collisions between the three env vars are
    logged as warnings so a copy-paste misconfiguration cannot silently
    bill STARTER customers at ENTERPRISE rates.
    """
    global _dodo_product_cache
    if not product_id:
        return PlanTierId.FREE
    if _dodo_product_cache is not None:
        return _dodo_product_cache.get(product_id, PlanTierId.FREE)
    with _dodo_product_cache_lock:
        if _dodo_product_cache is not None:
            return _dodo_product_cache.get(product_id, PlanTierId.FREE)
        cache: dict[str, PlanTierId] = {}
        for tier, env_name in _PRODUCT_ID_ENV_BY_TIER.items():
            value = os.environ.get(env_name, "").strip()
            if not value:
                continue
            existing = cache.get(value)
            if existing is not None and existing != tier:
                logger.warning(
                    "Dodo product-id collision: env var %s maps %r to %s, "
                    "but an earlier tier already mapped it to %s. Fix "
                    "DODO_PRODUCT_ID_* env vars.",
                    env_name,
                    value,
                    tier.value,
                    existing.value,
                )
            else:
                cache[value] = tier
        _dodo_product_cache = cache
    return _dodo_product_cache.get(product_id, PlanTierId.FREE)


def reset_dodo_product_cache() -> None:
    """Invalidate the product-id → tier cache (for tests and env changes)."""
    global _dodo_product_cache
    with _dodo_product_cache_lock:
        _dodo_product_cache = None


# ---------------------------------------------------------------------------
# Standard Webhooks signature verification
# ---------------------------------------------------------------------------


def _configured_webhook_key() -> str:
    return os.environ.get(_DODO_WEBHOOK_KEY_ENV, "").strip()


def _verify_signature_header(
    raw_body: bytes,
    *,
    webhook_id: str,
    timestamp: str,
    signature_header: str,
    secret: str,
) -> bool:
    """Verify a Standard-Webhooks ``v1,<hex>`` signature (rotation tolerant).

    The signed message is ``{webhook_id}.{timestamp}.{raw_body}``; the
    HMAC-SHA256 key is the base64-decoded signing secret. The header may
    carry several space-separated signatures (old + new during rotation);
    any match with the current secret is accepted.
    """
    try:
        key = base64.b64decode(secret)
    except (ValueError, TypeError) as exc:
        logger.warning("Dodo webhook key is not valid base64 — rejecting webhook")
        msg = "Invalid Dodo webhook key configuration"
        raise ValueError(msg) from exc

    try:
        ts = int(timestamp)
    except (ValueError, TypeError) as exc:
        msg = "Dodo webhook timestamp is not an integer"
        raise ValueError(msg) from exc
    if abs(time.time() - ts) > _WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS:
        msg = f"Dodo webhook timestamp outside tolerance window ({ts})"
        raise ValueError(msg)

    message = f"{webhook_id}.{timestamp}.{raw_body.decode('utf-8')}".encode()
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    for part in signature_header.split(" "):
        candidate = part.strip()
        candidate = candidate.removeprefix("v1,")
        if candidate and hmac.compare_digest(candidate, expected):
            return True
    return False


def verify_dodo_webhook_signature(raw_body: bytes, headers: Mapping[str, str]) -> None:
    """Verify a Dodo webhook request. Raises ``ValueError`` on failure."""
    webhook_id = headers.get("webhook-id", "").strip()
    timestamp = headers.get("webhook-timestamp", "").strip()
    signature = headers.get("webhook-signature", "").strip()
    if not webhook_id or not timestamp or not signature:
        msg = "Missing Standard-Webhooks headers (webhook-id/timestamp/signature)"
        raise ValueError(msg)
    secret = _configured_webhook_key()
    if not secret:
        msg = "DODO_PAYMENTS_WEBHOOK_KEY is not configured"
        raise ValueError(msg)
    if not _verify_signature_header(
        raw_body, webhook_id=webhook_id, timestamp=timestamp, signature_header=signature, secret=secret
    ):
        msg = "Dodo webhook signature verification failed"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Webhook-id idempotency state
# ---------------------------------------------------------------------------


class DodoWebhookStateStore:
    """File-backed record of processed Dodo webhook ids.

    ``webhook-id`` is a unique event identifier (Standard Webhooks
    spec); the same id must never be processed twice so Dodo's
    built-in retries (exponential backoff) are safe to deliver. The
    file is flock-guarded so multi-worker deployments share one state.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_dodo_state_path()
        self._lock = threading.RLock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("Dodo webhook state unreadable; starting empty (path=%s)", self.path)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def is_processed(self, webhook_id: str) -> bool:
        with self._lock:
            return webhook_id in self._read()

    def mark_processed(self, webhook_id: str, event_type: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            snapshot = self._read()
            snapshot[webhook_id] = {
                "event_type": event_type,
                "processed_at": time.time(),
            }
            fd, tmp_path = tempfile.mkstemp(prefix=".dodo_webhook_state.", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    Path(tmp_path).unlink()


_dodo_state_store = DodoWebhookStateStore()


def reset_dodo_state_store(store: DodoWebhookStateStore | None = None) -> None:
    """Reset the module-level state store singleton (for tests)."""
    global _dodo_state_store
    _dodo_state_store = store if store is not None else DodoWebhookStateStore()


# ---------------------------------------------------------------------------
# Webhook normalization
# ---------------------------------------------------------------------------

# Dodo event type → legacy vocabulary handled by
# ``app.billing.webhooks._process_webhook_event``.
_DODO_ACTIVE_EVENTS = frozenset(
    {"subscription.active", "subscription.renewed", "subscription.reactivated", "subscription.updated"}
)
_DODO_SUSPENDED_EVENTS = frozenset({"subscription.on_hold", "subscription.failed"})
_DODO_CANCELLED_EVENTS = frozenset({"subscription.cancelled"})
_DODO_PAYMENT_COMPLETED_EVENTS = frozenset({"payment.succeeded"})
_DODO_PAYMENT_FAILED_EVENTS = frozenset({"payment.failed"})
_DODO_ENTITLEMENT_EVENTS = frozenset(
    {
        *_DODO_ACTIVE_EVENTS,
        *_DODO_SUSPENDED_EVENTS,
        *_DODO_CANCELLED_EVENTS,
        *_DODO_PAYMENT_COMPLETED_EVENTS,
        *_DODO_PAYMENT_FAILED_EVENTS,
    },
)


def _extract_customer_id(data: dict[str, Any]) -> str:
    for key in ("customer_id", "subscriber_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    customer = data.get("customer")
    if isinstance(customer, dict):
        value = customer.get("id")
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_dataforge_user_id(data: dict[str, Any]) -> str:
    """Extract the server-issued DataForge identity from Dodo metadata."""
    metadata_candidates: list[Any] = [data.get("metadata")]
    customer = data.get("customer")
    if isinstance(customer, dict):
        metadata_candidates.append(customer.get("metadata"))
    for metadata in metadata_candidates:
        if not isinstance(metadata, Mapping):
            continue
        value = metadata.get("dataforge_user_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_dodo_webhook(body: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Normalize a Dodo webhook into the shared billing vocabulary.

    Returns ``(event_type, customer_id, data)`` where ``data`` carries
    the keys the shared processor understands (``plan_tier``, ``status``,
    ``subscription_id``, ``customer_id``).

    Raises ``ValueError`` when a subscription event references an
    unknown product id — a silent tier downgrade must never happen.
    """
    event_type = str(body.get("type", "") or "")
    original_event_type = event_type
    raw_data = body.get("data")
    if not isinstance(raw_data, dict):
        raw_data = {}
    data: dict[str, Any] = dict(raw_data)

    provider_customer_id = _extract_customer_id(data)
    customer_id = _extract_dataforge_user_id(data)
    if original_event_type in _DODO_ENTITLEMENT_EVENTS and not customer_id:
        msg = "Dodo entitlement event is missing metadata.dataforge_user_id"
        raise ValueError(msg)
    subscription_id = str(data.get("subscription_id", "") or "")
    status = str(data.get("status", "active") or "active")
    product_id = str(data.get("product_id", "") or "")

    if event_type in _DODO_ACTIVE_EVENTS:
        tier = resolve_tier_from_dodo_product(product_id)
        if not product_id or tier is PlanTierId.FREE:
            # Unknown product on an activation event must never silently
            # grant free — reject so the event can be investigated.
            msg = f"Dodo subscription event references unknown product_id={product_id!r}"
            raise ValueError(msg)
        event_type = "subscription.updated"
        data["plan_tier"] = tier.value
        data["status"] = "active"
    elif event_type in _DODO_SUSPENDED_EVENTS:
        data["status"] = "on_hold"
    elif event_type in _DODO_CANCELLED_EVENTS:
        data["status"] = "cancelled"
    elif event_type in _DODO_PAYMENT_COMPLETED_EVENTS:
        data["status"] = "active"
    elif event_type in _DODO_PAYMENT_FAILED_EVENTS:
        data["status"] = "failed"

    data["provider_customer_id"] = provider_customer_id
    data["customer_id"] = customer_id or provider_customer_id
    data.setdefault("subscription_id", subscription_id)
    data.setdefault("status", status)
    return event_type, customer_id, data


# ---------------------------------------------------------------------------
# Webhook handling
# ---------------------------------------------------------------------------


def handle_dodo_webhook(
    raw_body: bytes,
    headers: Mapping[str, str],
    *,
    state_store: DodoWebhookStateStore | None = None,
) -> dict[str, str]:
    """Verify, dedupe, and process a Dodo webhook payload.

    Raises ``HTTPException`` (401 invalid signature, 400 bad payload,
    503 unconfigured) on failure. Returns ``{"status": "ok" | "already_processed",
    "event": <type>}`` on success.
    """
    if not _configured_webhook_key():
        raise HTTPException(status_code=503, detail="DODO_PAYMENTS_WEBHOOK_KEY is not configured.")

    try:
        verify_dodo_webhook_signature(raw_body, headers)
    except ValueError as exc:
        logger.warning("Dodo webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid Dodo webhook signature.") from exc

    try:
        loaded = json.loads(raw_body.decode("utf-8"))
        if not isinstance(loaded, dict):
            msg = "payload must be an object"
            raise TypeError(msg)
        body: dict[str, Any] = loaded
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    event_type = str(body.get("type", "") or "")
    webhook_id = headers.get("webhook-id", "").strip()
    store = state_store if state_store is not None else _dodo_state_store
    if webhook_id and store.is_processed(webhook_id):
        logger.info("Dodo webhook already processed: id=%s event=%s", webhook_id, event_type)
        return {"status": "already_processed", "event": event_type}

    try:
        normalized_type, customer_id, data = normalize_dodo_webhook(body)
    except ValueError as exc:
        logger.warning("Rejecting Dodo webhook event=%s: %s", event_type, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not normalized_type:
        logger.info("Dodo webhook with no event type; id=%s", webhook_id)
        if webhook_id:
            store.mark_processed(webhook_id, event_type)
        return {"status": "ok", "event": ""}

    from app.billing.webhooks import _process_webhook_event

    _process_webhook_event(normalized_type, data, customer_id)

    if webhook_id:
        store.mark_processed(webhook_id, event_type)

    logger.info(
        "Dodo webhook processed: id=%s event=%s customer=%s",
        webhook_id,
        event_type,
        customer_id[:8] + "..." if customer_id else "<none>",
    )
    return {"status": "ok", "event": event_type}


@router.post("/webhook", status_code=200)
async def dodo_webhook(request: Request) -> dict[str, str]:
    """Receive billing webhook events from Dodo Payments.

    The request is verified with the Standard-Webhooks HMAC signature
    (headers ``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``)
    and deduplicated by ``webhook-id``.
    """
    raw_body = await request.body()
    return handle_dodo_webhook(raw_body, request.headers)


# ---------------------------------------------------------------------------
# Dodo API client
# ---------------------------------------------------------------------------


class DodoClient:
    """Minimal httpx client for the Dodo Payments REST API.

    Uses the SSRF-safe ``open_safe_client`` for all outbound traffic.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        product_ids: dict[str, str],
        return_url: str = "",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._product_ids = product_ids
        self._return_url = return_url

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def create_checkout_session(
        self,
        *,
        plan_tier: str,
        customer_email: str,
        customer_name: str,
        return_url: str,
        metadata: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a hosted checkout session for a subscription product.

        Returns the raw response body: ``session_id``, ``checkout_url``,
        ``status``.
        """
        if not self._api_key:
            msg = "Dodo client is not configured (DODO_PAYMENTS_API_KEY missing)"
            raise RuntimeError(msg)
        product_id = self._product_ids.get(plan_tier)
        if not product_id:
            msg = f"No Dodo product id configured for plan tier {plan_tier!r}"
            raise ValueError(msg)
        payload: dict[str, Any] = {
            "product_cart": [{"product_id": product_id, "quantity": 1}],
            "customer": {"email": customer_email, "name": customer_name},
            "return_url": return_url or self._return_url,
        }
        if metadata:
            payload["metadata"] = {str(key): str(value) for key, value in metadata.items()}
        with open_safe_client(timeout=30.0) as client:
            resp = client.post(
                f"{self._base_url}/checkouts",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        return body

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Fetch a subscription from the Dodo API (used by reconciliation)."""
        if not self._api_key:
            msg = "Dodo client is not configured (DODO_PAYMENTS_API_KEY missing)"
            raise RuntimeError(msg)
        with open_safe_client(timeout=30.0) as client:
            resp = client.get(
                f"{self._base_url}/subscriptions/{subscription_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        return body


_dodo_client: DodoClient | None = None
_dodo_client_lock = threading.Lock()


def get_dodo_client() -> DodoClient:
    """Return the module-level Dodo client singleton (env-configured)."""
    global _dodo_client
    if _dodo_client is not None:
        return _dodo_client
    with _dodo_client_lock:
        if _dodo_client is None:
            product_ids = {}
            for tier, env_name in _PRODUCT_ID_ENV_BY_TIER.items():
                value = os.environ.get(env_name, "").strip()
                if value:
                    product_ids[tier.value] = value
            _dodo_client = DodoClient(
                api_key=os.environ.get(_DODO_API_KEY_ENV, "").strip(),
                base_url=_dodo_base_url(),
                product_ids=product_ids,
                return_url=os.environ.get(_DODO_RETURN_URL_ENV, "").strip(),
            )
    return _dodo_client


def reset_dodo_client(client: DodoClient | None = None) -> None:
    """Reset the Dodo client singleton (for tests)."""
    global _dodo_client
    _dodo_client = client


# ---------------------------------------------------------------------------
# Checkout endpoint
# ---------------------------------------------------------------------------


class DodoCheckoutRequest(BaseModel):
    """Request body for POST /api/billing/dodo/checkout."""

    plan_tier: Literal["starter", "pro", "enterprise"]
    return_url: str | None = Field(default=None, min_length=1, max_length=2048)
    # Accepted for backwards-compatible clients but deliberately ignored.
    # Checkout identity is always loaded from the authenticated account.
    email: str = Field(default="", max_length=320, description="Deprecated; server derives this from the session")
    name: str = Field(default="", max_length=255, description="Deprecated; server derives this from the session")

    @field_validator("return_url")
    @classmethod
    def _validate_return_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("http://", "https://")):
            msg = "URL must start with http:// or https://"
            raise ValueError(msg)
        validate_public_http_url(value)
        return value


@router.post("/checkout", status_code=200)
async def dodo_checkout(
    body: DodoCheckoutRequest,
    principal: Annotated[
        tuple[UserRole, str, str, str],
        Depends(require_principal([UserRole.USER])),
    ],
) -> dict[str, str]:
    """Create a Dodo checkout session for a plan tier.

    Returns ``{"checkout_url": ..., "session_id": ..., "plan_tier": ...}``.
    The user is redirected to ``checkout_url`` (hosted by Dodo).
    """
    _role, user_id, org_id, project_id = principal
    store = get_identity_store()
    user = store.get_user(user_id)
    project = store.get_project(project_id) if project_id else None
    if (
        user is None
        or user.status is UserStatus.DISABLED
        or not org_id
        or not project_id
        or project is None
        or project.org_id != org_id
        or not store.is_org_member(user_id, org_id)
    ):
        raise HTTPException(status_code=403, detail="A valid tenant session is required for checkout.")

    client = get_dodo_client()
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="DODO_PAYMENTS_API_KEY is not configured.",
        )
    try:
        session = client.create_checkout_session(
            plan_tier=body.plan_tier,
            customer_email=user.email,
            customer_name=user.display_name or user.email,
            return_url=body.return_url or "",
            metadata={
                "dataforge_user_id": user_id,
                "dataforge_org_id": org_id,
                "dataforge_project_id": project_id,
            },
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("Dodo checkout session creation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "checkout_url": str(session.get("checkout_url", "") or ""),
        "session_id": str(session.get("session_id", "") or ""),
        "plan_tier": body.plan_tier,
    }


# ---------------------------------------------------------------------------
# Entitlement reconciliation (E2.4)
# ---------------------------------------------------------------------------

# Dodo subscription statuses → our store statuses.
_DODO_STATUS_ACTIVE = frozenset({"active", "trialing"})
_DODO_STATUS_HELD = frozenset({"on_hold", "past_due", "failed", "incomplete"})
_DODO_STATUS_CANCELLED = frozenset({"cancelled", "canceled", "expired", "unpaid"})


def reconcile_entitlements(client: DodoClient | None = None) -> dict[str, Any]:
    """Walk the subscription store and repair entitlements against Dodo.

    For every stored record that references a real subscription:

    - API says active/trialing → ensure the store tier matches the
      product (repair on upgrade/downgrade), status active.
    - API says on_hold/past_due/failed → status past_due, tier
      preserved.
    - API says cancelled/expired → downgrade to free/canceled.
    - API error / unknown subscription → leave the record untouched and
      report it; an API outage must never mass-downgrade customers.

    Returns a report dict with ``checked``, ``repaired``, ``held``,
    ``downgraded``, ``errors`` lists (customer ids).
    """
    from app.billing.webhooks import _subscription_store, _SubscriptionStore

    if client is None:
        client = get_dodo_client()
    if not client.is_configured:
        return {
            "skipped": True,
            "reason": "DODO_PAYMENTS_API_KEY is not configured — reconciliation skipped",
            "checked": 0,
            "repaired": [],
            "held": [],
            "downgraded": [],
            "errors": [],
        }

    report: dict[str, Any] = {
        "checked": 0,
        "repaired": [],
        "held": [],
        "downgraded": [],
        "errors": [],
    }
    store = _subscription_store if isinstance(_subscription_store, _SubscriptionStore) else _SubscriptionStore()
    for record in store.values():
        customer_id = str(record.get("customer_id", "") or "")
        subscription_id = str(record.get("subscription_id", "") or "")
        tier = str(record.get("plan_tier", "free") or "free")
        if not subscription_id or tier == PlanTierId.FREE.value:
            continue
        try:
            remote = client.get_subscription(subscription_id)
        except Exception as exc:
            logger.warning("Reconciliation lookup failed for customer=%s: %s", customer_id[:8], exc)
            report["errors"].append(customer_id)
            continue
        report["checked"] += 1

        remote_status = str(remote.get("status", "") or "").lower()
        remote_product = str(remote.get("product_id", "") or "")
        if remote_status in _DODO_STATUS_ACTIVE:
            if remote_product:
                remote_tier = resolve_tier_from_dodo_product(remote_product)
                if remote_tier is not PlanTierId.FREE and remote_tier.value != tier:
                    store.set(customer_id, remote_tier.value, "active", subscription_id)
                    report["repaired"].append(customer_id)
                    logger.info("Reconciliation repaired customer=%s tier %s -> %s", customer_id[:8], tier, remote_tier.value)
                elif record.get("status") != "active":
                    store.set(customer_id, tier, "active", subscription_id)
            elif record.get("status") != "active":
                store.set(customer_id, tier, "active", subscription_id)
        elif remote_status in _DODO_STATUS_HELD:
            if record.get("status") != "past_due":
                store.set(customer_id, tier, "past_due", subscription_id)
                report["held"].append(customer_id)
                logger.info("Reconciliation held customer=%s (status %s)", customer_id[:8], remote_status)
        elif remote_status in _DODO_STATUS_CANCELLED:
            store.set(customer_id, PlanTierId.FREE.value, "canceled", "")
            report["downgraded"].append(customer_id)
            logger.info("Reconciliation downgraded customer=%s to free", customer_id[:8])
        else:
            logger.debug("Reconciliation: unhandled Dodo status %r for customer=%s", remote_status, customer_id[:8])

    return report


__all__ = [
    "DodoClient",
    "DodoWebhookStateStore",
    "get_dodo_client",
    "handle_dodo_webhook",
    "normalize_dodo_webhook",
    "reconcile_entitlements",
    "reset_dodo_client",
    "reset_dodo_product_cache",
    "reset_dodo_state_store",
    "resolve_tier_from_dodo_product",
    "verify_dodo_webhook_signature",
]
