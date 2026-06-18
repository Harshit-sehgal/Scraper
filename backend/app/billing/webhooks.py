"""Webhook handler for billing events from Autumn/Stripe.

Processes subscription lifecycle events:
- subscription.created / subscription.updated — update user plan tiers
- subscription.canceled / subscription.expired — downgrade to free
- invoice.payment_failed — flag account as past_due
- customer.subscription.deleted — clean up

The webhook endpoint is mounted at POST /api/billing/webhook.
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
from app.config import settings
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])
_SIGNATURE_HEADERS = (
    "X-DataForge-Webhook-Signature",
    "X-Autumn-Signature",
    "X-Webhook-Signature",
)
_SECRET_HEADERS = (
    "X-DataForge-Webhook-Secret",
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
    for env_var in ("AUTUMN_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"):
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
    """Receive billing webhook events from Autumn/Stripe.

    This endpoint is called by Autumn/Stripe when subscription events
    occur. It processes the event and updates the local subscription
    state accordingly.

    Authentication: This endpoint uses the Autumn webhook secret for
    verification (in production), or the admin API key for testing.
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
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type: str = str(body.get("event_type", body.get("type", "")) or "")
    data: dict[str, Any] = body.get("data", {}) if isinstance(body, dict) else {}
    # Resolve the customer id from ``customer_id`` / ``customer`` only.
    # Do NOT fall back to ``data["id"]`` — that is the event/object id
    # in Stripe/Autumn payloads, not a customer id; using it would
    # persist a subscription record keyed by the event id and let a
    # later bogus event with the same id clobber a real customer.
    customer_id: str = str(data.get("customer_id", data.get("customer", "")) or "")

    logger.info("Billing webhook received: event=%s customer=%s", event_type, customer_id)

    if not event_type:
        return {"status": "skipped", "reason": "No event_type provided"}

    _process_webhook_event(event_type, data)

    return {"status": "ok", "event": event_type}


def _process_webhook_event(event_type: str, data: dict[str, Any]) -> None:
    """Internal processor for webhook events.

    Separated from the route handler for testability.
    """
    customer_id: str = ""
    if isinstance(data, dict):
        customer_id = str(data.get("customer_id", data.get("customer", "")) or "")

    if not customer_id:
        logger.warning("Webhook event %s has no customer_id", event_type)
        return

    if event_type in ("subscription.created", "subscription.updated", "customer.subscription.updated"):
        plan_name: str = "free"
        status: str = "active"
        sub_id: str = ""
        if isinstance(data, dict):
            for plan_key in ("plan", "plan_tier", "plan_name"):
                v = data.get(plan_key)
                if isinstance(v, str):
                    plan_name = v
                    break
            v = data.get("status")
            if isinstance(v, str):
                status = v
            for sub_key in ("subscription_id", "id"):
                v = data.get(sub_key)
                if isinstance(v, str):
                    sub_id = v
                    break

        # Normalize plan name (compare against PlanTierId values, which are lowercase)
        normalized_plan = plan_name.lower() if plan_name else "free"
        valid_tiers = {t.value for t in PlanTierId}
        if normalized_plan not in valid_tiers:
            normalized_plan = "free"

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

    elif event_type in ("subscription.canceled", "customer.subscription.deleted", "subscription.expired"):
        set_customer_subscription(
            customer_id=customer_id,
            tier=PlanTierId.FREE.value,
            status="canceled",
        )
        logger.info("Subscription %s: customer=%s downgraded to free", event_type, customer_id)

    elif event_type == "invoice.payment_failed":
        existing = get_customer_subscription(customer_id)
        if existing:
            # Single write that observes the latest disk snapshot — no
            # in-place mutation that would diverge if another process
            # changed the record between read and write.
            set_customer_subscription(
                customer_id=customer_id,
                tier=existing.get("plan_tier", PlanTierId.FREE.value),
                status=SubscriptionStatus.PAST_DUE.value,
                subscription_id=existing.get("subscription_id", ""),
            )
        logger.warning("Payment failed for customer=%s", customer_id)

    elif event_type == "customer.created":
        logger.info("Customer created: %s", customer_id)

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
