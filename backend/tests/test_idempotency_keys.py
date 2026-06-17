"""Tests for ``POST /api/jobs`` idempotency-key support.

When a client sends an ``Idempotency-Key`` header with a value
(<= 128 chars), the second and subsequent requests with the same
key return the same ``job_id`` instead of creating duplicates.
The first response carries ``idempotent_replay=False``; replays
carry ``idempotent_replay=True``.
"""

from __future__ import annotations


def _create_payload(suffix: str = "1") -> dict:
    return {
        "name": f"Idempotency Test {suffix}",
        "mode": "manual",
        "urls": [f"https://example.com/idem-{suffix}"],
        "topic": "idempotency",
    }


class TestIdempotencyHappyPath:
    def test_repeated_key_returns_same_job_id(self, client) -> None:
        headers = {"Idempotency-Key": "client-retry-001"}
        first = client.post("/api/jobs", json=_create_payload("1"), headers=headers)
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["idempotent_replay"] is False

        second = client.post("/api/jobs", json=_create_payload("1"), headers=headers)
        assert second.status_code == 200, second.text
        second_body = second.json()
        assert second_body["idempotent_replay"] is True
        assert second_body["job_id"] == first_body["job_id"]

    def test_repeated_key_with_different_payload_returns_409(self, client) -> None:
        headers = {"Idempotency-Key": "client-retry-conflict"}
        first = client.post("/api/jobs", json=_create_payload("A"), headers=headers)
        assert first.status_code == 200, first.text

        second = client.post("/api/jobs", json=_create_payload("B"), headers=headers)
        assert second.status_code == 409, second.text
        assert "Conflict" in second.json().get("detail", "")

    def test_different_keys_create_different_jobs(self, client) -> None:
        h1 = {"Idempotency-Key": "key-A"}
        h2 = {"Idempotency-Key": "key-B"}
        a = client.post("/api/jobs", json=_create_payload("A"), headers=h1)
        b = client.post("/api/jobs", json=_create_payload("B"), headers=h2)
        assert a.status_code == 200
        assert b.status_code == 200
        assert a.json()["job_id"] != b.json()["job_id"]
        assert a.json()["idempotent_replay"] is False
        assert b.json()["idempotent_replay"] is False

    def test_no_header_means_no_replay(self, client) -> None:
        a = client.post("/api/jobs", json=_create_payload("X"))
        b = client.post("/api/jobs", json=_create_payload("Y"))
        assert a.json()["idempotent_replay"] is False
        assert b.json()["idempotent_replay"] is False
        assert a.json()["job_id"] != b.json()["job_id"]


class TestIdempotencyValidation:
    def test_overlong_key_is_rejected(self, client) -> None:
        headers = {"Idempotency-Key": "x" * 200}
        r = client.post("/api/jobs", json=_create_payload(), headers=headers)
        assert r.status_code == 400
        assert "Idempotency-Key" in r.json().get("detail", "")


class TestIdempotencyStorage:
    def test_lookup_after_record(self, tmp_path, monkeypatch) -> None:
        from app.config import settings
        from app.job_store import (
            lookup_idempotency_key,
            record_idempotency_key,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            record_idempotency_key("abc-123", "job-xyz", "fingerprint-here")
            assert lookup_idempotency_key("abc-123") == "job-xyz"
            assert lookup_idempotency_key("never-seen") is None
            assert lookup_idempotency_key("") is None
        finally:
            reset_job_store_for_tests()

    def test_prune_removes_old_keys(self, tmp_path, monkeypatch) -> None:
        from app.config import settings
        from app.job_store import (
            _DB_LOCK,
            _get_connection,
            lookup_idempotency_key,
            prune_idempotency_keys,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            # Insert a row with a created_at well in the past.
            with _DB_LOCK:
                conn = _get_connection()
                try:
                    conn.execute(
                        """
                        INSERT INTO idempotency_keys
                            (idem_key, job_id, request_fingerprint, created_at)
                        VALUES (?, ?, ?, datetime('now', '-30 days'))
                        """,
                        ("ancient", "job-a", "fp"),
                    )
                    conn.commit()
                finally:
                    conn.close()
            assert lookup_idempotency_key("ancient") == "job-a"
            deleted = prune_idempotency_keys(older_than_days=7)
            assert deleted == 1
            assert lookup_idempotency_key("ancient") is None
        finally:
            reset_job_store_for_tests()

    def test_prune_does_not_remove_recent_keys(self, tmp_path, monkeypatch) -> None:
        """Keys created within the prune window must survive."""
        from app.config import settings
        from app.job_store import (
            lookup_idempotency_key,
            prune_idempotency_keys,
            record_idempotency_key,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            record_idempotency_key("recent", "job-r", "fp")
            deleted = prune_idempotency_keys(older_than_days=7)
            assert deleted == 0
            assert lookup_idempotency_key("recent") == "job-r"
        finally:
            reset_job_store_for_tests()

    def test_prune_zero_days_removes_nothing(self, tmp_path, monkeypatch) -> None:
        """Prune with older_than_days=0 should remove nothing."""
        from app.config import settings
        from app.job_store import (
            lookup_idempotency_key,
            prune_idempotency_keys,
            record_idempotency_key,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            record_idempotency_key("zero", "job-z", "fp")
            deleted = prune_idempotency_keys(older_than_days=0)
            assert deleted == 0
            assert lookup_idempotency_key("zero") == "job-z"
        finally:
            reset_job_store_for_tests()

    def test_record_empty_key_noop(self, tmp_path, monkeypatch) -> None:
        """record_idempotency_key with an empty key must not write anything."""
        from app.config import settings
        from app.job_store import (
            lookup_idempotency_key,
            record_idempotency_key,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            record_idempotency_key("", "job-empty", "fp")
            assert lookup_idempotency_key("") is None
        finally:
            reset_job_store_for_tests()

    def test_record_none_key_noop(self, tmp_path, monkeypatch) -> None:
        """record_idempotency_key with None key must not write anything."""
        from app.config import settings
        from app.job_store import (
            lookup_idempotency_key,
            record_idempotency_key,
            reset_job_store_for_tests,
        )

        monkeypatch.setenv("DATAFORGE_STATE_FILE", str(tmp_path / "idem_state.json"))
        monkeypatch.setattr(settings, "STATE_FILE_PATH", str(tmp_path / "idem_state.json"))
        reset_job_store_for_tests()
        try:
            record_idempotency_key(None, "job-none", "fp")  # type: ignore[arg-type]
            assert lookup_idempotency_key(None) is None  # type: ignore[arg-type]
        finally:
            reset_job_store_for_tests()
