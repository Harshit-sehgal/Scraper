"""Comp 11: Data processing records — test append-only processing log."""

from __future__ import annotations

import copy
import datetime
from typing import Any


class ProcessingRecord:
    """An append-only log entry for data processing activities."""

    def __init__(self, action: str, user_id: str, url: str, details: dict[str, Any] | None = None) -> None:
        self.timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        self.action = action
        self.user_id = user_id
        self.url = url
        self.details = details or {}
        self.entry_id = f"proc-{hash((self.timestamp, self.action, self.user_id, self.url)) % 10**6:06d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "url": self.url,
            "details": self.details,
        }


class ProcessingLog:
    """Append-only processing log. Records can only be read, not deleted."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, action: str, user_id: str, url: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = ProcessingRecord(action, user_id, url, details).to_dict()
        self._entries.append(entry)
        return entry

    def get_entries(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def query(self, user_id: str | None = None, action: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        results = self._entries
        if user_id:
            results = [e for e in results if e["user_id"] == user_id]
        if action:
            results = [e for e in results if e["action"] == action]
        return copy.deepcopy(results[-limit:])


class TestProcessingRecord:
    def test_record_has_required_fields(self) -> None:
        record = ProcessingRecord("extract", "user-1", "https://example.com")
        d = record.to_dict()
        assert "entry_id" in d
        assert "timestamp" in d
        assert "action" in d
        assert "user_id" in d
        assert "url" in d

    def test_details_optional(self) -> None:
        record = ProcessingRecord("extract", "user-1", "https://example.com")
        assert record.to_dict()["details"] == {}

    def test_details_stored(self) -> None:
        record = ProcessingRecord("export", "user-2", "https://example.com", {"format": "csv", "records": 100})
        assert record.to_dict()["details"]["format"] == "csv"


class TestProcessingLog:
    def test_append_only(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-1", "https://example.com")
        log.record("extract", "user-1", "https://example2.com")
        assert log.count() == 2

    def test_get_entries_returns_copy(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-1", "https://example.com")
        entries = log.get_entries()
        entries.pop()
        assert log.count() == 1

    def test_entries_immutable_via_api(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-1", "https://example.com")
        log.record("extract", "user-2", "https://example2.com")
        entries = log.get_entries()
        entries.pop()
        assert log.count() == 2

    def test_no_delete_method_on_api(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-1", "https://example.com")
        assert not hasattr(log, "delete")

    def test_query_by_user(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-a", "https://a.com")
        log.record("extract", "user-b", "https://b.com")
        log.record("extract", "user-a", "https://c.com")
        results = log.query(user_id="user-a")
        assert len(results) == 2

    def test_query_by_action(self) -> None:
        log = ProcessingLog()
        log.record("extract", "user-1", "https://a.com")
        log.record("export", "user-1", "https://a.com")
        log.record("delete", "user-1", "https://a.com")
        results = log.query(action="export")
        assert len(results) == 1
