"""Unit tests for review_queue.

Covers submission, pending retrieval, approval, rejection,
nonexistent-ID handling, field correction convenience, and clearing.
"""

from __future__ import annotations

import pytest
from app import review_queue as rq
from app import structured_job_logs as sjl

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    """Reset both the review queue and job events stores."""
    rq.clear_review_queue()
    sjl.clear_job_events()


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class TestSubmitForReview:
    """submit_for_review creates a pending ReviewItem."""

    def test_creates_item_with_pending_status(self) -> None:
        """A newly submitted item has status 'pending'."""
        item = rq.submit_for_review("job-1", "rec-1", reason="low_quality")
        d = item.to_dict()
        assert d["job_id"] == "job-1"
        assert d["record_id"] == "rec-1"
        assert d["reason"] == "low_quality"
        assert d["status"] == "pending"
        assert d["review_id"]  # non-empty

    def test_field_errors_stored(self) -> None:
        """Field errors and original values are persisted."""
        item = rq.submit_for_review(
            "job-f",
            "rec-f",
            field_errors={"price": "missing"},
            original_values={"price": None},
        )
        d = item.to_dict()
        assert d["field_errors"]["price"] == "missing"
        assert d["original_values"]["price"] is None

    def test_review_id_is_unique(self) -> None:
        """Each submission gets a distinct review_id."""
        item_a = rq.submit_for_review("job-u", "rec-a")
        item_b = rq.submit_for_review("job-u", "rec-b")
        assert item_a.review_id != item_b.review_id


# ---------------------------------------------------------------------------
# get_pending_reviews
# ---------------------------------------------------------------------------


class TestGetPendingReviews:
    """get_pending_reviews returns pending items sorted by submission time."""

    def test_returns_pending_items(self) -> None:
        """Only items with pending status are returned."""
        item = rq.submit_for_review("job-p", "rec-p")
        pending = rq.get_pending_reviews()
        assert len(pending) == 1
        assert pending[0]["review_id"] == item.review_id

    def test_excludes_non_pending(self) -> None:
        """Approved/rejected items do not appear in pending list."""
        item = rq.submit_for_review("job-np", "rec-np")
        rq.approve_review(item.review_id)
        pending = rq.get_pending_reviews()
        assert len(pending) == 0

    def test_pagination(self) -> None:
        """limit and offset control the returned page."""
        for i in range(5):
            rq.submit_for_review("job-pag", f"rec-{i}")
        page = rq.get_pending_reviews(limit=2, offset=0)
        assert len(page) == 2

    def test_most_recent_first(self) -> None:
        """Items are returned with the most recently submitted first."""
        item_a = rq.submit_for_review("job-ord", "rec-a")
        item_b = rq.submit_for_review("job-ord", "rec-b")
        pending = rq.get_pending_reviews()
        assert pending[0]["review_id"] == item_b.review_id
        assert pending[1]["review_id"] == item_a.review_id


# ---------------------------------------------------------------------------
# approve_review
# ---------------------------------------------------------------------------


class TestApproveReview:
    """approve_review marks a pending item as approved."""

    def test_changes_status_to_approved(self) -> None:
        """After approval the status is 'approved'."""
        item = rq.submit_for_review("job-ap", "rec-ap")
        result = rq.approve_review(item.review_id, corrected_fields={"title": "New"}, reviewer="alice")
        assert result is True
        d = rq.get_review(item.review_id)
        assert d is not None
        assert d["status"] == "approved"
        assert d["corrected_fields"]["title"] == "New"
        assert d["reviewer"] == "alice"

    def test_returns_false_for_nonexistent(self) -> None:
        """Approving a nonexistent review_id returns False."""
        assert rq.approve_review("no-such-id") is False

    def test_returns_false_for_already_approved(self) -> None:
        """Approving an already-approved item returns False."""
        item = rq.submit_for_review("job-aa", "rec-aa")
        rq.approve_review(item.review_id)
        assert rq.approve_review(item.review_id) is False


# ---------------------------------------------------------------------------
# reject_review
# ---------------------------------------------------------------------------


class TestRejectReview:
    """reject_review marks a pending item as rejected."""

    def test_changes_status_to_rejected(self) -> None:
        """After rejection the status is 'rejected'."""
        item = rq.submit_for_review("job-rj", "rec-rj")
        result = rq.reject_review(item.review_id, reviewer="bob")
        assert result is True
        d = rq.get_review(item.review_id)
        assert d is not None
        assert d["status"] == "rejected"
        assert d["reviewer"] == "bob"

    def test_returns_false_for_nonexistent(self) -> None:
        """Rejecting a nonexistent review_id returns False."""
        assert rq.reject_review("no-such-id") is False

    def test_returns_false_for_already_rejected(self) -> None:
        """Rejecting an already-rejected item returns False."""
        item = rq.submit_for_review("job-ar", "rec-ar")
        rq.reject_review(item.review_id)
        assert rq.reject_review(item.review_id) is False

    def test_cannot_approve_after_rejection(self) -> None:
        """An already-rejected item cannot be approved."""
        item = rq.submit_for_review("job-arp", "rec-arp")
        rq.reject_review(item.review_id)
        assert rq.approve_review(item.review_id) is False


# ---------------------------------------------------------------------------
# correct_record_field
# ---------------------------------------------------------------------------


class TestCorrectRecordField:
    """correct_record_field creates an already-approved correction entry."""

    def test_creates_approved_entry(self) -> None:
        """The returned dict has status 'approved' with the corrected field."""
        d = rq.correct_record_field("job-cf", "rec-cf", "price", 9.99, reviewer="carol")
        assert d is not None
        assert d["status"] == "approved"
        assert d["corrected_fields"]["price"] == 9.99
        assert d["reviewer"] == "carol"

    def test_reason_includes_field_name(self) -> None:
        """The reason string tags the corrected field name."""
        d = rq.correct_record_field("job-rs", "rec-rs", "title", "Fixed")
        assert "title" in d["reason"]


# ---------------------------------------------------------------------------
# clear_review_queue
# ---------------------------------------------------------------------------


class TestClearReviewQueue:
    """clear_review_queue empties the entire queue."""

    def test_clears_all_items(self) -> None:
        """After clear, the queue is empty."""
        rq.submit_for_review("j1", "r1")
        rq.submit_for_review("j2", "r2")
        rq.clear_review_queue()
        assert rq.get_pending_reviews() == []
        assert rq.get_review("j1") is None
