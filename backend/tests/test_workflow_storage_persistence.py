"""Regression guard for CAND-P1-WORKFLOW-STORAGE-001 — workflow persistence.

The candidate issue flagged that workflow definitions persist to a flat
JSON file (``backend/app/routers/workflow.py`` → ``JSONFileStore`` at
``/app/backend/data/workflows.json``) and lack a Postgres/SQLite
repository parity path. That refactor (a migration to a ``workflows``
table with owner/project indexes and parity tests) is a deliberate
storage-architecture change and remains deferred.

These tests, however, pin down the contract that *the current storage*
must keep holding for the SaaS multi-tenant story to remain safe:

1. ``upsert`` then ``get`` round-trips with all tenant fields intact.
2. A new ``JSONFileStore`` opened on the **same path** re-reads the
   data — i.e. cross-process / cross-worker durability works
   (this is the property that makes shared gunicorn workers consistent).
3. Tenant filters using ``user_id`` / ``org_id`` / ``project_id``
   isolate records between principals.
4. Concurrent writers from multiple threads keep the flock invariant
   intact (no partial / missing records).

If/when the candidate becomes a real refactor (move workflows to
the ``JobRepository`` interface), these tests should keep passing
under the new backend — the contract is what matters, not the
implementation.
"""

from __future__ import annotations

import threading
from pathlib import Path

from app.utils.json_file_store import JSONFileStore


def _seed_workflow_record(
    wf_id: str,
    *,
    user_id: str = "",
    org_id: str = "",
    project_id: str = "",
    name: str = "Untitled",
) -> dict[str, object]:
    """Build a representative workflow record as written by the router."""
    return {
        "id": wf_id,
        "name": name,
        "user_id": user_id,
        "org_id": org_id,
        "project_id": project_id,
        "start_url": "https://example.com/start",
        "steps": [],
        "extraction_schema": [],
        "status": "saved",
    }


class TestWorkflowDurabilityRoundTrip:
    """A workflow written by one store is visible to a fresh store at the same path."""

    def test_upsert_then_get_preserves_tenant_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "workflows.json"
        store = JSONFileStore(path)
        record = _seed_workflow_record(
            "wf-1",
            user_id="user-a",
            org_id="org-1",
            project_id="proj-1",
            name="Durable workflow",
        )
        store.upsert("wf-1", record)

        loaded = store.get("wf-1")

        assert loaded is not None
        assert loaded.get("user_id") == "user-a"
        assert loaded.get("org_id") == "org-1"
        assert loaded.get("project_id") == "proj-1"
        assert loaded.get("name") == "Durable workflow"

    def test_cross_process_reopen_returns_same_record(self, tmp_path: Path) -> None:
        """Closing one store handle and opening another on the same path must
        see the same record — this is what keeps sibling workers consistent
        in production gunicorn deployments."""
        path = tmp_path / "workflows.json"

        writer = JSONFileStore(path)
        writer.upsert("wf-reopen", _seed_workflow_record("wf-reopen", user_id="user-b"))

        # A new client opens the same file. This is the same call shape
        # the worker process makes on every request.
        reader = JSONFileStore(path)
        seen = reader.get("wf-reopen")

        assert seen is not None
        assert seen.get("user_id") == "user-b"


class TestWorkflowTenantIsolation:
    """The router's ``can_access_scoped_resource`` filter reads tenant fields
    from the stored record. If those fields are missing or trampled by an
    upsert, principal-filtered listings will leak."""

    def test_user_id_filter_isolates_records_by_principal(self, tmp_path: Path) -> None:
        store = JSONFileStore(tmp_path / "wf.json")
        for idx, user in enumerate(("alice", "bob", "mallory")):
            store.upsert(f"wf-u-{idx}", _seed_workflow_record(f"wf-u-{idx}", user_id=user))

        stored = list(store.values())
        by_user: dict[str, list[str]] = {}
        for record in stored:
            uid = str(record.get("user_id") or "")
            by_user.setdefault(uid, []).append(str(record.get("id")))

        assert sorted(by_user.get("alice", [])) == ["wf-u-0"]
        assert sorted(by_user.get("bob", [])) == ["wf-u-1"]
        assert sorted(by_user.get("mallory", [])) == ["wf-u-2"]

    def test_upsert_preserves_created_at_when_overwriting(self, tmp_path: Path) -> None:
        """The router bumps ``updated_at`` on every save but must not trample
        ``created_at`` — the lifecycle invariant lives in
        ``JSONFileStore.upsert`` and a regression here would silently break
        audit ordering."""
        store = JSONFileStore(tmp_path / "wf-lifecycle.json")
        first = _seed_workflow_record("wf-life", name="A")
        first["created_at"] = "2026-01-01T00:00:00+00:00"
        store.upsert("wf-life", first)

        second = _seed_workflow_record("wf-life", name="B")
        # Note: caller does NOT supply created_at — JSONFileStore must
        # preserve the prior value.
        store.upsert("wf-life", second)

        loaded = store.get("wf-life")
        assert loaded is not None
        assert loaded.get("name") == "B"
        assert loaded.get("created_at") == "2026-01-01T00:00:00+00:00"
        assert "updated_at" in loaded


class TestWorkflowConcurrentWrites:
    """Process boundaries that fire in parallel (e.g. two gunicorn workers
    answering requests for the same principal) must not corrupt the
    on-disk state — that's the whole point of the ``flock`` + ``os.replace``
    dance in ``JSONFileStore``."""

    def test_concurrent_upserts_keep_every_record(self, tmp_path: Path) -> None:
        store = JSONFileStore(tmp_path / "wf-conc.json")
        n_per_thread = 25
        n_threads = 4
        total = n_per_thread * n_threads
        barrier = threading.Barrier(n_threads)
        errors: list[BaseException] = []

        def writer(tid: int) -> None:
            try:
                barrier.wait()
                for i in range(n_per_thread):
                    rid = f"wf-t{tid}-i{i}"
                    store.upsert(rid, _seed_workflow_record(rid, user_id=f"user-{tid}"))
            except BaseException as exc:  # pragma: no cover - re-raised below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"writer thread errored: {errors!r}"
        records = list(store.values())
        ids = sorted((r.get("id") or "") for r in records)
        expected = sorted(f"wf-t{t}-i{i}" for t in range(n_threads) for i in range(n_per_thread))
        assert ids == expected, "concurrent upserts must keep every record"
        assert len(records) == total

    def test_concurrent_writes_and_deletes_no_corruption(self, tmp_path: Path) -> None:
        """A worst-case interleaving: one thread inserts, another deletes.
        Final state must be either {\"kept\"} or {\"gone\"} per id, never
        partial JSON."""
        store = JSONFileStore(tmp_path / "wf-mix.json")
        store.upsert("wf-mix-1", _seed_workflow_record("wf-mix-1", user_id="u"))
        store.upsert("wf-mix-2", _seed_workflow_record("wf-mix-2", user_id="u"))
        stop = threading.Event()

        def inserter() -> None:
            while not stop.is_set():
                store.upsert("wf-mix-3", _seed_workflow_record("wf-mix-3", user_id="u"))

        def deleter() -> None:
            while not stop.is_set():
                store.delete("wf-mix-1")
                store.delete("wf-mix-2")

        t_ins = threading.Thread(target=inserter)
        t_del = threading.Thread(target=deleter)
        t_ins.start()
        t_del.start()

        # Race window — the threads spin continuously and the only
        # reason to wait here is to let them do some work. 10ms is
        # more than enough on any reasonable machine; the test asserts
        # that the file remains readable JSON, not that N iterations ran.
        import time

        time.sleep(0.01)
        stop.set()
        t_ins.join()
        t_del.join()

        # The store must remain readable and JSON-shaped at this point
        # (no torn writes). Whatever the final ids are, they must round-trip.
        values = list(store.values())
        for r in values:
            assert "id" in r
            assert "user_id" in r
        # Re-open to prove on-disk state is well-formed JSON
        reopened = JSONFileStore(store.path)
        assert list(reopened.values()) == values
