"""Review Queue — manual review workflow for low-quality extraction results.

When extraction quality is below a configurable threshold, records can be
routed to a review queue where a human operator can correct fields and
approve them. Approved corrections feed back into the extraction pipeline
for future runs.

The store is in-memory with a global lock for thread safety.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from app import structured_job_logs

logger = __import__("logging").getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_REVIEW_STATUS_PENDING = "pending"
_REVIEW_STATUS_APPROVED = "approved"
_REVIEW_STATUS_REJECTED = "rejected"


class ReviewItem:
    """A single item in the review queue."""

    __slots__ = (
        "corrected_fields",
        "field_errors",
        "job_id",
        "original_values",
        "reason",
        "record_id",
        "resolved_at",
        "review_id",
        "reviewer",
        "status",
        "submitted_at",
    )

    def __init__(
        self,
        *,
        job_id: str,
        record_id: str,
        reason: str = "",
        field_errors: dict[str, str] | None = None,
        original_values: dict[str, Any] | None = None,
    ) -> None:
        self.review_id: str = uuid.uuid4().hex[:12]
        self.job_id: str = job_id
        self.record_id: str = record_id
        self.reason: str = reason
        self.field_errors: dict[str, str] = field_errors or {}
        self.original_values: dict[str, Any] = original_values or {}
        self.corrected_fields: dict[str, Any] = {}
        self.status: str = _REVIEW_STATUS_PENDING
        self.submitted_at: float = time.time()
        self.resolved_at: float | None = None
        self.reviewer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "job_id": self.job_id,
            "record_id": self.record_id,
            "reason": self.reason,
            "field_errors": self.field_errors,
            "original_values": self.original_values,
            "corrected_fields": self.corrected_fields,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "resolved_at": self.resolved_at,
            "reviewer": self.reviewer,
        }


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

_review_queue: dict[str, ReviewItem] = {}
_review_queue_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def submit_for_review(
    job_id: str,
    record_id: str,
    *,
    reason: str = "",
    field_errors: dict[str, str] | None = None,
    original_values: dict[str, Any] | None = None,
) -> ReviewItem:
    """Submit a record for human review.

    Returns the :class:`ReviewItem` with its assigned ``review_id``.
    """
    item = ReviewItem(
        job_id=job_id,
        record_id=record_id,
        reason=reason,
        field_errors=field_errors,
        original_values=original_values,
    )
    with _review_queue_lock:
        _review_queue[item.review_id] = item
    structured_job_logs.log_job_event(
        job_id,
        "review_submitted",
        {"review_id": item.review_id, "record_id": record_id, "reason": reason},
    )
    logger.info("Submitted record %s from job %s for review (reason=%s)", record_id, job_id, reason)
    return item


def get_pending_reviews(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Return pending review items, most recent first, up to *limit*."""
    with _review_queue_lock:
        pending = [item.to_dict() for item in _review_queue.values() if item.status == _REVIEW_STATUS_PENDING]
    pending.sort(key=lambda d: d["submitted_at"], reverse=True)
    return pending[offset : offset + limit]


def get_review(review_id: str) -> dict[str, Any] | None:
    """Return a single review item by ID, or ``None``."""
    with _review_queue_lock:
        item = _review_queue.get(review_id)
    return item.to_dict() if item else None


def approve_review(
    review_id: str,
    *,
    corrected_fields: dict[str, Any] | None = None,
    reviewer: str = "",
) -> bool:
    """Approve a review, optionally supplying field corrections.

    Returns ``True`` if the review existed and was pending, ``False`` otherwise.
    """
    with _review_queue_lock:
        item = _review_queue.get(review_id)
        if item is None or item.status != _REVIEW_STATUS_PENDING:
            return False
        item.status = _REVIEW_STATUS_APPROVED
        item.corrected_fields = corrected_fields or {}
        item.resolved_at = time.time()
        item.reviewer = reviewer or "anonymous"

    structured_job_logs.log_job_event(
        item.job_id,
        "review_approved",
        {"review_id": review_id, "record_id": item.record_id, "corrected_fields": item.corrected_fields},
    )
    logger.info("Approved review %s for record %s in job %s", review_id, item.record_id, item.job_id)
    return True


def reject_review(review_id: str, *, reviewer: str = "") -> bool:
    """Reject a review. Returns ``True`` if found and pending."""
    with _review_queue_lock:
        item = _review_queue.get(review_id)
        if item is None or item.status != _REVIEW_STATUS_PENDING:
            return False
        item.status = _REVIEW_STATUS_REJECTED
        item.resolved_at = time.time()
        item.reviewer = reviewer or "anonymous"

    structured_job_logs.log_job_event(
        item.job_id,
        "review_rejected",
        {"review_id": review_id, "record_id": item.record_id},
    )
    logger.info("Rejected review %s for record %s in job %s", review_id, item.record_id, item.job_id)
    return True


def correct_record_field(
    job_id: str,
    record_id: str,
    field_name: str,
    corrected_value: Any,
    *,
    reviewer: str = "",
) -> dict[str, Any] | None:
    """Human-in-the-loop correction: set a single field on a record.

    Creates a review entry (approved) for auditability.
    Returns the review dict or ``None`` on error.
    """
    item = submit_for_review(
        job_id,
        record_id,
        reason=f"field_correction:{field_name}",
        field_errors={field_name: "incorrect"},
    )
    approve_review(item.review_id, corrected_fields={field_name: corrected_value}, reviewer=reviewer)
    return item.to_dict()


def clear_review_queue() -> None:
    """Drop all review items (used by tests and reset)."""
    with _review_queue_lock:
        _review_queue.clear()
