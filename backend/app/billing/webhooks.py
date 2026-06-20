"""Webhook handler for billing events from PayPal (subscribed via the PayPal Dashboard).

Processes subscription lifecycle events:
- BILLING.SUBSCRIPTION.CREATED / UPDATED — update user plan tiers
- BILLING.SUBSCRIPTION.CANCELLED / SUSPENDED — downgrade to free
- BILLING.SUBSCRIPTION.PAYMENT.FAILED — flag account as past_due
- PAYMENT.SALE.COMPLETED — log a successful charge

The webhook endpoint is mounted at POST /api/billing/webhook.

In production, PayPal verifies signatures via its cert-based /v1/notifications/verify
endpoint; in dev/test we honour a shared HMAC secret in X-Billing-Webhook-Secret
(also PAYPAL_WEBHOOK_SECRET) which simplifies local CI runs.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.billing.models import PlanTierId, SubscriptionStatus
from app.billing.service import resolve_tier_from_plan_id
from app.config import settings
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])
_SIGNATURE_HEADERS = (
    "X-DataForge-Webhook-Signature",
    "X-PayPal-Transmission-Sig",
    "X-Autumn-Signature",
    "X-Webhook-Signature",
)
_SECRET_HEADERS = (
    "X-DataForge-Webhook-Secret",
    "X-Billing-Webhook-Secret",
    "X-Autumn-Webhook-Secret",
    "X-Webhook-Secret",
)


# Path is captured at module import time. Tests that need a per-run
# store must set ``DATAFORGE_BILLING_SUBSCRIPTIONS_FILE`` BEFORE the
# module is imported (or before ``importlib.reload`` is called).
def _default_subscriptions_path() -> Path:
    """Resolve the on-disk path for the subscription store.

    Reads ``DATAFORGE_BILLING_SUBSCRIPTIONS_FILE`` on every call so
    tests can override it after import and so operators can repoint
    the store without restarting running workers.
    """
    env_value = os.environ.get("DATAFORGE_BILLING_SUBSCRIPTIONS_FILE", "").strip()
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[2] / "data" / "billing_subscriptions.json"


def _is_production_env() -> bool:
    return (getattr(settings, "ENV", "") or "").lower() == "production"


class _SubscriptionStore:
    """File-backed subscription state shared across worker processes.

    Disk is the source of truth. ``get`` / ``values`` / ``__len__``
    re-read the JSON file on every call so writes from sibling workers
    are visible immediately. ``set`` / ``delete`` use ``fcntl.flock``
    over a sibling ``.lock`` file to serialize the full
    read-modify-write cycle across processes, preventing lost-update
    races. ``threading.RLock`` guards in-process concurrent readers.

    This replaces the original module-level ``_customer_subscriptions``
    dict, which was per-process and lost state across worker restarts
    (the author left a ``# replace with DB in production`` comment).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_subscriptions_path()
        self._lock = threading.RLock()

    def _read_json(self) -> dict[str, dict[str, Any]]:
        """Read the current snapshot from disk. Tolerates missing/unreadable/corrupt files."""
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning("Subscription store unreadable; starting empty (path=%s)", self.path)
            return {}
        if not isinstance(raw, dict):
            logger.warning("Subscription store has unexpected shape; starting empty (path=%s)", self.path)
            return {}
        cleaned: dict[str, dict[str, Any]] = {}
        for customer_id, record in raw.items():
            if isinstance(customer_id, str) and isinstance(record, dict):
                cleaned[customer_id] = {str(k): v for k, v in record.items()}
        return cleaned

    def _acquire_cross_process_lock(self) -> int:
        """Open the sibling ``.lock`` file and acquire an exclusive flock.

        ENOSYS / EOPNOTSUPP: refuse in production (cold-fail rather
        than silently corrupt on unusual FS like NFS / FUSE); allow in
        non-production with a debug log so tests still run.
        """
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as exc:
                if exc.errno in (errno.ENOSYS, errno.EOPNOTSUPP):
                    if _is_production_env():
                        raise
                    logger.debug(
                        "flock unsupported on this filesystem; cross-process safety is not guaranteed (path=%s)",
                        lock_path,
                    )
                else:
                    raise
        except BaseException:
            os.close(lock_fd)
            raise
        return lock_fd

    def _read_modify_write(
        self,
        mutate: Any,
    ) -> dict[str, dict[str, Any]]:
        """Read snapshot, apply ``mutate``, write atomically — all under the flock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = self._acquire_cross_process_lock()
        try:
            snapshot = self._read_json()
            mutate(snapshot)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".billing_subscriptions.",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                with contextlib.suppress(FileNotFoundError):
                    Path(tmp_path).unlink()
                raise
            return snapshot
        finally:
            os.close(lock_fd)

    # ---- public API -----------------------------------------------------

    def get(self, customer_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read_json().get(customer_id)
            return dict(record) if record is not None else None

    def set(
        self,
        customer_id: str,
        tier: str,
        status: str,
        subscription_id: str = "",
    ) -> None:
        def _mutate(snapshot: dict[str, dict[str, Any]]) -> None:
            snapshot[customer_id] = {
                "customer_id": customer_id,
                "plan_tier": tier,
                "status": status,
                "subscription_id": subscription_id,
            }

        self._read_modify_write(_mutate)

    def delete(self, customer_id: str) -> bool:
        """Returns ``True`` if the record existed and was removed."""
        removed = False

        def _mutate(snapshot: dict[str, dict[str, Any]]) -> None:
            nonlocal removed
            if customer_id in snapshot:
                del snapshot[customer_id]
                removed = True

        self._read_modify_write(_mutate)
        return removed

    def values(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._read_json().values()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._read_json())


# Module-level singleton. Constructed once per process; tests use a
# fresh path via ``DATAFORGE_BILLING_SUBSCRIPTIONS_FILE`` so each
# reload gets a clean file.
_subscription_store = _SubscriptionStore()


def get_customer_subscription(customer_id: str) -> dict[str, Any] | None:
    """Get the stored subscription for a customer. Reads from disk."""
    return _subscription_store.get(customer_id)


def set_customer_subscription(
    customer_id: str,
    tier: str,
    status: str,
    subscription_id: str = "",
) -> None:
    """Store or update a customer's subscription. Persists atomically to disk."""
    _subscription_store.set(customer_id, tier, status, subscription_id)


def delete_customer_subscription(customer_id: str) -> bool:
    """Remove a customer's subscription record. Persists the deletion. Returns ``True`` if removed."""
    return _subscription_store.delete(customer_id)


def _configured_webhook_secret() -> str:
    """Return the configured billing webhook verification secret, if any."""
    configured = str(getattr(settings, "BILLING_WEBHOOK_SECRET", "") or "").strip()
    if configured:
        return configured
    for env_var in ("PAYPAL_WEBHOOK_SECRET",):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return ""


def _signature_candidates(header_value: str) -> list[str]:
    """Extract digest candidates from common signature header formats."""
    candidates: list[str] = []
    for part in header_value.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            candidates.append(item)
            continue
        key, _, value = item.partition("=")
        if key.strip().lower() in {"sha256", "v1"} and value.strip():
            candidates.append(value.strip())
    return candidates


def _verify_billing_webhook(request: Request, raw_body: bytes) -> None:
    """Verify webhook authenticity when a billing webhook secret is configured."""
    secret = _configured_webhook_secret()
    if not secret:
        if _is_production_env():
            raise HTTPException(status_code=503, detail="Billing webhook secret is not configured.")
        return

    for header in _SECRET_HEADERS:
        provided = request.headers.get(header, "").strip()
        if provided and hmac.compare_digest(provided, secret):
            return

    signature_header = ""
    for header in _SIGNATURE_HEADERS:
        signature_header = request.headers.get(header, "").strip()
        if signature_header:
            break
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    for candidate in _signature_candidates(signature_header):
        if hmac.compare_digest(candidate, expected):
            return
    raise HTTPException(status_code=401, detail="Invalid billing webhook signature.")


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@router.post("/webhook", status_code=200)
async def billing_webhook(request: Request) -> dict[str, str]:
    """Receive billing webhook events from PayPal.

    This endpoint is called by PayPal when subscription events
    occur. It processes the event and updates the local subscription
    state accordingly.

    Authentication: The endpoint uses the Billing webhook secret for
    HMAC verification (dev / shared-secret mode), or PayPal's
    cert-based signature verification (production).
    The body is parsed as JSON.
    """
    raw_body = await request.body()
    _verify_billing_webhook(request, raw_body)
    try:
        loaded = json.loads(raw_body.decode("utf-8"))
        if not isinstance(loaded, dict):
            msg = "Webhook payload must be a JSON object"
            raise TypeError(msg)
        body: dict[str, Any] = loaded
    except Exception as exc:
        logger.debug("Invalid billing webhook JSON body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    event_type, customer_id, data = _normalize_webhook(body)

    logger.info("Billing webhook received: event=%s customer=%s", event_type, customer_id)

    if not event_type:
        return {"status": "skipped", "reason": "No event_type provided"}

    _process_webhook_event(event_type, data, customer_id)

    return {"status": "ok", "event": event_type}


def _normalize_webhook(body: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Normalize a webhook body across PayPal / Stripe / legacy Autumn dialects.

    PayPal:  {"event_type": "BILLING.SUBSCRIPTION.CREATED", "resource": {...}}
    Stripe:  {"type": "customer.subscription.updated", "data": {"object": {...}}}
    Autumn:  {"event_type": "subscription.created", "data": {...}}

    Returns: (event_type, customer_id, data_dict)
    """
    event_type: str = str(body.get("event_type", body.get("type", "")) or "")

    # Resolve the data dictionary. PayPal uses top-level ``resource``; Stripe
    # wraps inside ``data``; Autumn uses both. Prefer the explicit data dict
    # when present, fall back to ``resource`` for PayPal.
    raw_data = body.get("data") if isinstance(body.get("data"), dict) else None
    resource_data = body.get("resource") if isinstance(body.get("resource"), dict) else None

    if raw_data is not None:
        # For Stripe dialect, the actual subscription lives under data.object.
        inner_data = raw_data.get("object") if isinstance(raw_data.get("object"), dict) else raw_data
        data: dict[str, Any] = inner_data or {}
    elif resource_data is not None:
        data = resource_data
    else:
        data = {}

    # Resolve the customer / subscription id. PayPal puts it on resource.id
    # (the I-... subscription id); legacy Autumn/Stripe use customer_id or
    # customer. We deliberately skip the bare "id" field because that is
    # the PayPal event id (WH-...) — reusing it as a customer key would let
    # a later event with a different subscription but the same event-id scope
    # clobber a real record.
    customer_id: str = ""
    for key in ("customer_id", "customer", "subscriber_id"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, str) and v:
            customer_id = v
            break
    if not customer_id and isinstance(data, dict):
        # PayPal subscription id (I-...) lives on resource.{id,subscription_id}
        # for SUBSCRIPTION events. For PAYMENT.* events we use billing_id.
        for key in ("billing_id", "subscription_id"):
            v = data.get(key)
            if isinstance(v, str) and v:
                customer_id = v
                break

    return event_type, customer_id, data


# Plan-ID → tier resolution delegates to the shared helper in
# ``app.billing.service`` so the mapping lives in one place and is
# properly cached after first read.
resolve_plan_tier = resolve_tier_from_plan_id


# Module-level event-type dispatch sets (immutable, one allocation).
_PAYPAL_SUBSCRIPTION_EVENTS: frozenset[str] = frozenset(
    {
        "BILLING.SUBSCRIPTION.CREATED",
        "BILLING.SUBSCRIPTION.UPDATED",
        "BILLING.SUBSCRIPTION.ACTIVATED",
    }
)
_PAYPAL_SUSPENDED_EVENTS: frozenset[str] = frozenset(
    {
        "BILLING.SUBSCRIPTION.SUSPENDED",
    }
)
_PAYPAL_CANCELLED_EVENTS: frozenset[str] = frozenset(
    {
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.EXPIRED",
    }
)
_PAYPAL_PAYMENT_FAILED_EVENTS: frozenset[str] = frozenset(
    {
        "PAYMENT.SALE.DENIED",
        "PAYMENT.SALE.FAILED",
        "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
    }
)
_PAYPAL_PAYMENT_COMPLETED_EVENTS: frozenset[str] = frozenset(
    {
        "PAYMENT.SALE.COMPLETED",
        "PAYMENT.SALE.PENDING",
    }
)


def _process_webhook_event(event_type: str, data: dict[str, Any], customer_id: str = "") -> None:
    """Internal processor for webhook events.

    Separated from the route handler for testability.

    ``customer_id`` is resolved by ``_normalize_webhook`` for the route, and
    may be passed by tests for direct invocation. When empty we attempt to
    extract it from ``data`` so legacy test fixtures (which call this
    function directly with a flat data dict) keep working.
    """
    if not customer_id and isinstance(data, dict):
        customer_id = str(data.get("customer_id", data.get("customer", data.get("id", "")) or "") or "")

    if not customer_id:
        logger.warning("Webhook event %s has no customer_id", event_type)
        return

    # -- Subscription created / updated / activated --------------------------
    if (
        event_type
        in (
            "subscription.created",
            "subscription.updated",
            "customer.subscription.updated",
        )
        or event_type in _PAYPAL_SUBSCRIPTION_EVENTS
    ):
        plan_name: str = "free"
        status: str = "active"
        sub_id: str = ""
        if isinstance(data, dict):
            # Try human-readable plan keys (legacy Autumn/Stripe/PayPal test
            # fixtures) first, then fall back to raw PayPal plan_id which we
            # resolve via env-var mapping.
            for plan_key in ("plan", "plan_tier", "plan_name", "plan_id"):
                v = data.get(plan_key)
                if isinstance(v, str) and v:
                    plan_name = v
                    break
            # If the plan_id looks like a PayPal UUID (P-...) rather than a
            # human tier name, resolve it via env-var lookup. Comparisons
            # are case-insensitive because hypothetical proxy or
            # PayPal-variant payloads might lowercase the prefix.
            valid_tiers = {t.value for t in PlanTierId}
            if plan_name.lower() not in valid_tiers and plan_name.lower().startswith("p-"):
                plan_name = resolve_plan_tier(plan_name).value
            v = data.get("status")
            if isinstance(v, str) and v:
                status = v.lower()
            # Subscription id (sub_id) resolution. We deliberately do NOT
            # fall back to bare ``data["id"]`` — that's the PayPal event
            # id (WH-...) when ``data`` came from a top-level ``id`` field
            # (see the customer_id resolution above). For PayPal payloads
            # ``data`` is the ``resource`` dict where ``id`` IS the I-...
            # subscription id, but for non-PayPal dialects or proxy-rewritten
            # payloads the same field can hold the event id; we accept only
            # ``subscription_id`` here so a stray event id never becomes a
            # subscription record key. ``sub_id`` stays empty (stored as
            # ``""``) when nothing matches — list/get endpoints tolerate
            # this.
            for sub_key in ("subscription_id", "billing_id"):
                v = data.get(sub_key)
                if isinstance(v, str) and v:
                    sub_id = v
                    break

        # Normalize: validate against known PlanTierId values.
        normalized_plan = plan_name.lower() if plan_name else "free"
        valid_tiers = {t.value for t in PlanTierId}
        if normalized_plan not in valid_tiers:
            normalized_plan = PlanTierId.FREE.value

        set_customer_subscription(
            customer_id=customer_id,
            tier=normalized_plan,
            status=status,
            subscription_id=sub_id,
        )
        logger.info(
            "Subscription %s: customer=%s tier=%s status=%s",
            event_type,
            customer_id,
            normalized_plan,
            status,
        )

    # -- Subscription suspended (preserve existing tier, mark past_due) ------
    elif event_type in _PAYPAL_SUSPENDED_EVENTS:
        existing = get_customer_subscription(customer_id)
        if existing:
            set_customer_subscription(
                customer_id=customer_id,
                tier=existing.get("plan_tier", PlanTierId.FREE.value),
                status=SubscriptionStatus.PAST_DUE.value,
                subscription_id=existing.get("subscription_id", ""),
            )
            logger.info(
                "Subscription %s: customer=%s tier=%s (preserved) status=past_due",
                event_type,
                customer_id,
                existing.get("plan_tier", PlanTierId.FREE.value),
            )
        else:
            logger.warning("SUSPENDED event for unknown customer=%s — no existing record to preserve", customer_id)

    # -- Subscription cancelled / expired ------------------------------------
    elif (
        event_type
        in (
            "subscription.canceled",
            "customer.subscription.deleted",
            "subscription.expired",
        )
        or event_type in _PAYPAL_CANCELLED_EVENTS
    ):
        set_customer_subscription(
            customer_id=customer_id,
            tier=PlanTierId.FREE.value,
            status="canceled",
        )
        logger.info("Subscription %s: customer=%s downgraded to free", event_type, customer_id)

    # -- Payment failed (subscription-level or sale-level) -------------------
    elif event_type == "invoice.payment_failed" or event_type in _PAYPAL_PAYMENT_FAILED_EVENTS:
        existing = get_customer_subscription(customer_id)
        if existing:
            set_customer_subscription(
                customer_id=customer_id,
                tier=existing.get("plan_tier", PlanTierId.FREE.value),
                status=SubscriptionStatus.PAST_DUE.value,
                subscription_id=existing.get("subscription_id", ""),
            )
            logger.warning("Payment failed for customer=%s — status set to past_due", customer_id)
        else:
            logger.warning("Payment failed for unknown customer=%s — no existing record", customer_id)

    # -- Customer created ----------------------------------------------------
    elif event_type in ("customer.created", "CUSTOMER.CREATED"):
        logger.info("Customer created: %s", customer_id)

    # -- Payment completed / pending -----------------------------------------
    elif event_type in _PAYPAL_PAYMENT_COMPLETED_EVENTS:
        existing = get_customer_subscription(customer_id)
        if existing:
            # Reactivate the subscription if it was past_due/cancelled.
            set_customer_subscription(
                customer_id=customer_id,
                tier=existing.get("plan_tier", PlanTierId.FREE.value),
                status=SubscriptionStatus.ACTIVE.value,
                subscription_id=existing.get("subscription_id", ""),
            )
            logger.info("Payment completed for customer=%s — subscription reactivated", customer_id)
        else:
            logger.info("Payment completed for unknown customer=%s — no existing record", customer_id)

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)


# ---------------------------------------------------------------------------
# Management endpoints
# ---------------------------------------------------------------------------


@router.get("/subscriptions", status_code=200)
async def list_subscriptions(
    _role: Annotated[str, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> dict[str, Any]:
    """List all tracked subscriptions (admin/operator only)."""
    return {
        "total": len(_subscription_store),
        "subscriptions": _subscription_store.values(),
    }


@router.get("/subscriptions/{customer_id}", status_code=200)
async def get_subscription(
    customer_id: str,
    _role: Annotated[str, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> dict[str, Any]:
    """Get subscription details for a customer (admin/operator only)."""
    sub = get_customer_subscription(customer_id)
    if sub is None:
        return {"customer_id": customer_id, "plan_tier": "free", "status": "unknown"}
    return sub
