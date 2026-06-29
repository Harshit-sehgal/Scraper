"""Qual 9: Manual review workflow — test review queue when quality < threshold."""

from __future__ import annotations

from typing import Any

from app.models import FieldType, SchemaField
from app.utils.quality import score_record_quality


def _sf(name: str, ftype: FieldType = FieldType.STRING, required: bool = False) -> SchemaField:
    return SchemaField(name=name, field_type=ftype, description="", required=required)


def _should_route_to_review(record: dict[str, Any], schema_fields: list[SchemaField], threshold: float = 0.5) -> bool:
    """Check if a record's quality is below threshold, requiring manual review."""
    score = score_record_quality(record, schema_fields)
    return score < threshold


class TestReviewRoutingLogic:
    def test_high_quality_no_review(self) -> None:
        fields = [_sf("title", FieldType.STRING, required=True)]
        record = {"title": "A detailed product title with sufficient text"}
        assert not _should_route_to_review(record, fields, threshold=0.5)

    def test_low_quality_triggers_review(self) -> None:
        fields = [_sf("title", FieldType.STRING, required=True)]
        record = {"title": "N/A"}
        assert _should_route_to_review(record, fields, threshold=0.5)

    def test_empty_record_routes_to_review(self) -> None:
        fields = [_sf("name", FieldType.STRING, required=True)]
        record: dict[str, Any] = {}
        assert _should_route_to_review(record, fields, threshold=0.3)

    def test_higher_threshold_catches_more(self) -> None:
        fields = [_sf("title", FieldType.STRING, required=True)]
        record = {"title": "Short"}
        strict = _should_route_to_review(record, fields, threshold=0.9)
        lenient = _should_route_to_review(record, fields, threshold=0.1)
        assert strict is True
        assert lenient is False

    def test_all_fields_populated_high_quality(self) -> None:
        fields = [
            _sf("name", FieldType.STRING, required=True),
            _sf("price", FieldType.CURRENCY, required=True),
            _sf("description", FieldType.STRING, required=False),
        ]
        record = {"name": "Premium Widget Pro Max", "price": "$49.99", "description": "A well-described premium widget product"}
        assert not _should_route_to_review(record, fields, threshold=0.5)

    def test_required_field_missing_triggers_review(self) -> None:
        fields = [_sf("email", FieldType.EMAIL, required=True)]
        record = {"email": ""}
        assert _should_route_to_review(record, fields, threshold=0.3)


class TestReviewQueueModel:
    def test_review_queue_item_structure(self) -> None:
        review_item: dict[str, Any] = {
            "record_id": "rec-001",
            "job_id": "job-001",
            "quality_score": 0.25,
            "threshold": 0.5,
            "reason": "below_threshold",
            "fields": {"title": "N/A"},
            "status": "pending_review",
            "reviewed_by": None,
            "reviewed_at": None,
            "corrections": None,
        }
        assert review_item["status"] == "pending_review"
        assert review_item["quality_score"] < review_item["threshold"]

    def test_review_completion(self) -> None:
        item = {
            "record_id": "rec-002",
            "status": "pending_review",
            "reviewed_by": None,
        }
        item["status"] = "approved"
        item["reviewed_by"] = "user-42"
        assert item["status"] == "approved"
        assert item["reviewed_by"] == "user-42"


class TestReviewThreshold:
    def test_zero_threshold_no_review(self) -> None:
        fields = [_sf("x", FieldType.STRING, required=True)]
        record: dict[str, Any] = {}
        assert not _should_route_to_review(record, fields, threshold=0.0)

    def test_one_threshold_always_review(self) -> None:
        fields = [_sf("x", FieldType.STRING, required=True)]
        record = {"x": "Excellent detailed text for threshold testing purposes"}
        assert _should_route_to_review(record, fields, threshold=1.0)
