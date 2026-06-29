"""Qual 11: Data freshness monitoring — test freshness/staleness tracking for recurring jobs."""
from __future__ import annotations

import datetime
from typing import Any


def _staleness_status(
    last_refreshed: str | None,
    staleness_threshold_days: int = 7,
) -> dict[str, Any]:
    """Return freshness info for a record based on its last refresh time."""
    if last_refreshed is None:
        return {"fresh": False, "staleness_days": None, "status": "never_refreshed"}
    now = datetime.datetime.now(datetime.UTC)
    try:
        last = datetime.datetime.fromisoformat(last_refreshed)
        if last.tzinfo is None:
            last = last.replace(tzinfo=datetime.UTC)
        delta = now - last
        days = delta.total_seconds() / 86400
    except (ValueError, TypeError):
        return {"fresh": False, "staleness_days": None, "status": "invalid_date"}
    is_fresh = days < staleness_threshold_days
    if is_fresh:
        return {"fresh": True, "staleness_days": round(days, 1), "status": "fresh"}
    return {"fresh": False, "staleness_days": round(days, 1), "status": "stale"}


def _freshness_summary(records: list[dict], url_field: str = "source_url") -> dict[str, Any]:
    """Compute freshness summary across records."""
    statuses = {}
    for r in records:
        url = r.get(url_field, "unknown")
        last_refreshed = r.get("last_refreshed")
        statuses[url] = _staleness_status(last_refreshed)
    fresh_count = sum(1 for s in statuses.values() if s["fresh"])
    stale_count = sum(1 for s in statuses.values() if not s["fresh"])
    return {
        "total_urls": len(statuses),
        "fresh": fresh_count,
        "stale": stale_count,
        "freshness_pct": round(fresh_count / max(len(statuses), 1) * 100, 1),
        "urls": statuses,
    }


class TestStalenessDetection:
    def test_recently_refreshed_is_fresh(self) -> None:
        recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).isoformat()
        result = _staleness_status(recent, staleness_threshold_days=7)
        assert result["fresh"] is True
        assert result["status"] == "fresh"

    def test_old_data_is_stale(self) -> None:
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)).isoformat()
        result = _staleness_status(old, staleness_threshold_days=7)
        assert result["fresh"] is False
        assert result["status"] == "stale"

    def test_never_refreshed_is_stale(self) -> None:
        result = _staleness_status(None)
        assert result["fresh"] is False
        assert result["status"] == "never_refreshed"

    def test_invalid_date_string(self) -> None:
        result = _staleness_status("not-a-date")
        assert result["fresh"] is False
        assert result["status"] == "invalid_date"

    def test_empty_string_treated_as_never(self) -> None:
        result = _staleness_status("")
        assert result["fresh"] is False


class TestFreshnessSummary:
    def test_mixed_freshness(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        records = [
            {"source_url": "https://a.com/1", "last_refreshed": (now - datetime.timedelta(hours=1)).isoformat()},
            {"source_url": "https://a.com/2", "last_refreshed": (now - datetime.timedelta(days=30)).isoformat()},
            {"source_url": "https://a.com/3", "last_refreshed": None},
        ]
        summary = _freshness_summary(records)
        assert summary["fresh"] == 1
        assert summary["stale"] == 2

    def test_all_fresh_records(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        records = [
            {"source_url": "https://x.com/1", "last_refreshed": now.isoformat()},
            {"source_url": "https://x.com/2", "last_refreshed": now.isoformat()},
        ]
        summary = _freshness_summary(records)
        assert summary["freshness_pct"] == 100.0

    def test_all_stale_records(self) -> None:
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=365)).isoformat()
        records = [
            {"source_url": "https://y.com/1", "last_refreshed": old},
            {"source_url": "https://y.com/2", "last_refreshed": old},
        ]
        summary = _freshness_summary(records)
        assert summary["freshness_pct"] == 0.0

    def test_empty_records(self) -> None:
        summary = _freshness_summary([])
        assert summary["total_urls"] == 0
        assert summary["freshness_pct"] == 0.0

    def test_custom_threshold(self) -> None:
        recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)).isoformat()
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)).isoformat()
        result_recent = _staleness_status(recent, staleness_threshold_days=7)
        result_old = _staleness_status(old, staleness_threshold_days=7)
        assert result_recent["fresh"] is True
        assert result_old["fresh"] is False
