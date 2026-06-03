"""
Unit Tests for the JSON State Store.
Tests state persistence: loading, saving, path resolution, and recovery of
in-progress jobs after restart.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.models import Job, JobStatus
from app.state_store import (
    get_state_file_path,
    load_state,
    save_state,
)

_JOB_KWARGS: dict[str, Any] = {
    "url": "https://example.com",
    "schema_fields": [],
    "callback_url": None,
    "callback_headers": None,
    "filters": [],
    "webhook_url": None,
}


def _make_job_json(
    id: str,
    status: str,
    result: dict | None = None,
    name: str = "test-job",
) -> dict:
    return {
        "id": id,
        "name": name,
        "status": status,
        "result": result or {},
        "created_at": "2026-01-01T00:00:00",
        "url": "https://example.com",
        "schema_fields": [],
        "callback_url": None,
        "callback_headers": None,
        "filters": [],
        "webhook_url": None,
    }


# ─── get_state_file_path ────────────────────────────────────────────────


class TestGetStateFilePath:
    def test_default_path(self) -> None:
        """Without env override, returns the default data file path."""
        old = os.environ.pop("DATAFORGE_STATE_FILE", None)
        try:
            path = get_state_file_path()
            assert isinstance(path, Path)
            assert path.name == "jobs_state.json"
            assert "data" in str(path)
        finally:
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old

    def test_configured_path(self) -> None:
        """With env override, returns the configured path."""
        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = "/tmp/test_state.json"
            path = get_state_file_path()
            assert str(path) == "/tmp/test_state.json"
        finally:
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)


# ─── load_state ─────────────────────────────────────────────────────────


class TestLoadState:
    def test_no_file_returns_empty(self) -> None:
        """When the state file doesn't exist, returns empty stores."""
        # Use a path that doesn't exist
        old = os.environ.get("DATAFORGE_STATE_FILE")
        os.environ["DATAFORGE_STATE_FILE"] = "/tmp/nonexistent-state-file.json"
        try:
            jobs, recycle, world_state = load_state()
            assert jobs == {}
            assert recycle == {}
            assert world_state is None
        finally:
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_load_valid_jobs(self) -> None:
        """Loads valid jobs from a state file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "jobs": [_make_job_json("job-1", "completed")],
                    "recycle_bin": [],
                },
                f,
            )
            fpath = f.name

        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = fpath
            jobs, recycle, world_state = load_state()
            assert "job-1" in jobs
            assert jobs["job-1"].status == JobStatus.COMPLETED
            assert recycle == {}
        finally:
            os.unlink(fpath)
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_load_with_recycle_bin(self) -> None:
        """Loads both jobs and recycle bin entries."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "jobs": [],
                    "recycle_bin": [_make_job_json("deleted-job", "completed")],
                },
                f,
            )
            fpath = f.name

        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = fpath
            jobs, recycle, world_state = load_state()
            assert jobs == {}
            assert "deleted-job" in recycle
        finally:
            os.unlink(fpath)
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_recovery_marks_in_progress_as_failed(self) -> None:
        """Jobs that were in progress during shutdown are marked FAILED on load."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "jobs": [
                        _make_job_json("pending-job", "pending"),
                        _make_job_json("running-job", "running"),
                        _make_job_json("completed-job", "completed"),
                    ],
                    "recycle_bin": [],
                },
                f,
            )
            fpath = f.name

        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = fpath
            jobs, recycle, world_state = load_state()
            assert jobs["pending-job"].status == JobStatus.FAILED
            assert jobs["running-job"].status == JobStatus.FAILED
            assert jobs["completed-job"].status == JobStatus.COMPLETED
        finally:
            os.unlink(fpath)
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_corrupted_file_returns_empty(self) -> None:
        """A corrupted state file should not crash, returns empty."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("this is not json")
            fpath = f.name

        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = fpath
            jobs, recycle, world_state = load_state()
            assert jobs == {}
            assert recycle == {}
        finally:
            os.unlink(fpath)
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_skip_invalid_job_entries(self) -> None:
        """Malformed job entries are skipped gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "jobs": [
                        {"id": "bad-job"},  # Missing required fields
                        _make_job_json("good-job", "completed"),
                    ],
                    "recycle_bin": [],
                },
                f,
            )
            fpath = f.name

        old = os.environ.get("DATAFORGE_STATE_FILE")
        try:
            os.environ["DATAFORGE_STATE_FILE"] = fpath
            jobs, recycle, world_state = load_state()
            assert "bad-job" not in jobs
            assert "good-job" in jobs
        finally:
            os.unlink(fpath)
            if old is not None:
                os.environ["DATAFORGE_STATE_FILE"] = old
            else:
                os.environ.pop("DATAFORGE_STATE_FILE", None)


# ─── save_state ─────────────────────────────────────────────────────────


class TestSaveState:
    def test_save_creates_file(self) -> None:
        """Saving state creates a valid JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "test_state.json")
            old = os.environ.get("DATAFORGE_STATE_FILE")
            try:
                os.environ["DATAFORGE_STATE_FILE"] = fpath

                job = Job(
                    id="save-test",
                    name="test-job",
                    status=JobStatus.COMPLETED,
                    results=[{"key": "value"}],
                    created_at="2026-01-01T00:00:00",
                    **_JOB_KWARGS,
                )
                save_state({"save-test": job}, {})

                # Wait for the background thread to write (up to 3s)
                import time

                for _ in range(30):
                    if os.path.exists(fpath):
                        break
                    time.sleep(0.1)

                assert os.path.exists(fpath)
                data = json.loads(Path(fpath).read_text())
                assert "jobs" in data
                assert "recycle_bin" in data
                assert "saved_at" in data
                assert data["jobs"][0]["id"] == "save-test"
            finally:
                if old is not None:
                    os.environ["DATAFORGE_STATE_FILE"] = old
                else:
                    os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_save_and_reload_roundtrip(self) -> None:
        """State survives a save-then-load roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "roundtrip.json")
            old = os.environ.get("DATAFORGE_STATE_FILE")
            try:
                os.environ["DATAFORGE_STATE_FILE"] = fpath

                job = Job(
                    id="roundtrip-job",
                    name="test-job",
                    status=JobStatus.COMPLETED,
                    results=[{"items": ["a", "b"]}],
                    created_at="2026-01-01T00:00:00",
                    **_JOB_KWARGS,
                )
                save_state({"roundtrip-job": job}, {})

                import time

                for _ in range(30):
                    if os.path.exists(fpath):
                        break
                    time.sleep(0.1)

                jobs, recycle, world_state = load_state()
                assert "roundtrip-job" in jobs
                assert jobs["roundtrip-job"].results == [{"items": ["a", "b"]}]
                assert jobs["roundtrip-job"].status == JobStatus.COMPLETED
            finally:
                if old is not None:
                    os.environ["DATAFORGE_STATE_FILE"] = old
                else:
                    os.environ.pop("DATAFORGE_STATE_FILE", None)

    def test_save_with_recycle_bin(self) -> None:
        """Recycle bin entries are persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "recycle.json")
            old = os.environ.get("DATAFORGE_STATE_FILE")
            try:
                os.environ["DATAFORGE_STATE_FILE"] = fpath

                deleted_job = Job(
                    id="deleted",
                    name="deleted-job",
                    status=JobStatus.FAILED,
                    results=[],
                    created_at="2026-01-01T00:00:00",
                    **_JOB_KWARGS,
                )
                save_state({}, {"deleted": deleted_job})

                import time

                for _ in range(30):
                    if os.path.exists(fpath):
                        break
                    time.sleep(0.1)

                jobs, recycle, world_state = load_state()
                assert "deleted" in recycle
            finally:
                if old is not None:
                    os.environ["DATAFORGE_STATE_FILE"] = old
                else:
                    os.environ.pop("DATAFORGE_STATE_FILE", None)
