"""Unit Tests for Job Results Store.

Tests compression, streaming, and deletion of record datasets to/from disk
with mocked state file paths and error injection.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.utils.job_results_store import (
    delete_job_results_from_disk,
    get_job_results_path,
    get_results_dir,
    load_job_results_from_disk,
    load_job_results_from_disk_safe,
    load_paginated_job_results_from_disk,
    save_job_results_to_disk,
)


@pytest.fixture
def mock_state_path(tmp_path: Path) -> Iterator[Path]:
    """Fixture: create a temporary state directory and mock get_state_file_path."""
    state_file = tmp_path / "state" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{}")
    with patch("app.state_store.get_state_file_path", return_value=state_file):
        yield state_file


class TestGetResultsDir:
    def test_creates_results_directory(self, mock_state_path: Path) -> None:
        expected = mock_state_path.parent / "results"
        assert not expected.exists()
        result = get_results_dir()
        assert result == expected
        assert result.exists()
        assert result.is_dir()

    def test_idempotent(self, mock_state_path: Path) -> None:
        expected = mock_state_path.parent / "results"
        r1 = get_results_dir()
        r2 = get_results_dir()
        assert r1 == r2 == expected


class TestGetJobResultsPath:
    def test_returns_correct_path(self, mock_state_path: Path) -> None:
        path = get_job_results_path("job_abc")
        expected = mock_state_path.parent / "results" / "results_job_abc.jsonl.gz"
        assert path == expected
        assert path.suffixes == [".jsonl", ".gz"]


class TestSaveJobResultsToDisk:
    def test_saves_records_successfully(self, mock_state_path: Path) -> None:
        results = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        path_str = save_job_results_to_disk("job_save_1", results)

        path = Path(path_str)
        assert path.exists()
        assert path.suffixes == [".jsonl", ".gz"]

        # Verify content
        with gzip.open(path, "rt", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        assert lines[0] == {"id": 1, "name": "Alice"}
        assert lines[1] == {"id": 2, "name": "Bob"}

    def test_saves_empty_list(self, mock_state_path: Path) -> None:
        path_str = save_job_results_to_disk("job_empty", [])
        path = Path(path_str)
        assert path.exists()

        with gzip.open(path, "rt", encoding="utf-8") as f:
            content = f.read()
        assert content == ""  # Empty list → empty file

    def test_error_cleans_up_temp_file(self, mock_state_path: Path) -> None:
        """When gzip write fails, the temp file should be cleaned up."""
        class FailingWriter:
            def __enter__(self_):
                return self_

            def __exit__(self_, *args):
                pass

            def write(self_, _data):
                raise OSError("Disk full")

        with patch("gzip.open", return_value=FailingWriter()):
            with pytest.raises(OSError, match="Disk full"):
                save_job_results_to_disk("job_fail", [{"id": 1}])

        # Temp file should be gone
        results_dir = mock_state_path.parent / "results"
        temp_files = list(results_dir.glob("*.tmp"))
        assert len(temp_files) == 0, f"Temp files not cleaned up: {temp_files}"


class TestLoadJobResultsFromDisk:
    def test_loads_saved_records(self, mock_state_path: Path) -> None:
        # First save, then load
        results = [{"x": 10}, {"x": 20}]
        save_job_results_to_disk("job_load_1", results)

        loaded = load_job_results_from_disk("job_load_1")
        assert loaded == results

    def test_returns_empty_list_when_file_not_found(self, mock_state_path: Path) -> None:
        loaded = load_job_results_from_disk("nonexistent_job")
        assert loaded == []

    def test_raises_on_corrupt_data(self, mock_state_path: Path) -> None:
        # Write corrupt gzip data
        path = get_job_results_path("corrupt_job")
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write("not valid json\n")

        with pytest.raises(json.JSONDecodeError):
            load_job_results_from_disk("corrupt_job")


class TestLoadPaginatedJobResultsFromDisk:
    """Tests for paginated loading of job results from disk."""

    def test_loads_first_page(self, mock_state_path: Path) -> None:
        results = [{f"record_{i}": i} for i in range(100)]
        save_job_results_to_disk("pag_job", results)

        page, total = load_paginated_job_results_from_disk("pag_job", limit=10, offset=0)
        assert total == 100
        assert len(page) == 10
        assert page[0]["record_0"] == 0
        assert page[9]["record_9"] == 9

    def test_offsets_correctly(self, mock_state_path: Path) -> None:
        results = [{f"record_{i}": i} for i in range(100)]
        save_job_results_to_disk("pag_job2", results)

        page, total = load_paginated_job_results_from_disk("pag_job2", limit=10, offset=90)
        assert total == 100
        assert len(page) == 10
        assert page[0]["record_90"] == 90
        assert page[9]["record_99"] == 99

    def test_returns_empty_when_offset_past_end(self, mock_state_path: Path) -> None:
        results = [{f"record_{i}": i} for i in range(10)]
        save_job_results_to_disk("pag_job3", results)

        page, total = load_paginated_job_results_from_disk("pag_job3", limit=10, offset=20)
        assert total == 10
        assert len(page) == 0

    def test_returns_empty_when_file_missing(self, mock_state_path: Path) -> None:
        page, total = load_paginated_job_results_from_disk("nonexistent")
        assert total == 0
        assert page == []


class TestLoadJobResultsFromDiskSafe:
    """Tests for corruption-tolerant loading of job results."""

    def test_returns_valid_data_without_warning(self, mock_state_path: Path) -> None:
        results = [{"a": 1}, {"b": 2}]
        save_job_results_to_disk("safe_job", results)

        records, warning = load_job_results_from_disk_safe("safe_job")
        assert records == results
        assert warning is None

    def test_missing_file_returns_empty_no_warning(self, mock_state_path: Path) -> None:
        records, warning = load_job_results_from_disk_safe("ghost")
        assert records == []
        assert warning is None

    def test_corrupt_gzip_returns_partial_with_warning(self, mock_state_path: Path) -> None:
        # Write valid records then append garbage
        path = get_job_results_path("corrupt_gzip")
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create a truncated gzip by writing valid gzip data and then appending raw data
        with gzip.open(path, "wb") as f:
            f.write(b'{"valid": 1}\n')
        # Append non-gzip bytes after the valid gzip stream
        with open(path, "ab") as f:
            f.write(b"NOT GZIP DATA")

        records, warning = load_job_results_from_disk_safe("corrupt_gzip")
        # Should still get the valid record
        assert len(records) >= 1
        assert warning is not None
        assert "truncated" in warning.lower() or "corrupt" in warning.lower()

    def test_corrupt_json_line_returns_partial_with_warning(self, mock_state_path: Path) -> None:
        path = get_job_results_path("corrupt_json")
        path.parent.mkdir(parents=True, exist_ok=True)

        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write('{"valid": 1}\n')
            f.write('NOT JSON\n')
            f.write('{"valid": 3}\n')

        records, warning = load_job_results_from_disk_safe("corrupt_json")
        assert len(records) == 1
        assert records[0]["valid"] == 1
        assert warning is not None
        assert "Corrupt record at line 2" in warning


class TestDeleteJobResultsFromDisk:
    def test_deletes_existing_file(self, mock_state_path: Path) -> None:
        save_job_results_to_disk("job_del_1", [{"id": 1}])
        path = get_job_results_path("job_del_1")
        assert path.exists()

        result = delete_job_results_from_disk("job_del_1")
        assert result is True
        assert not path.exists()

    def test_returns_false_when_file_not_found(self, mock_state_path: Path) -> None:
        result = delete_job_results_from_disk("ghost_job")
        assert result is False

    def test_returns_false_on_delete_error(self, mock_state_path: Path) -> None:
        save_job_results_to_disk("job_del_fail", [{"id": 1}])
        real_path = get_job_results_path("job_del_fail")
        assert real_path.exists()

        # Use MagicMock(spec=Path) since PosixPath C attributes are read-only
        failing_path = MagicMock(spec=Path)
        failing_path.exists.return_value = True
        failing_path.unlink.side_effect = PermissionError("Access denied")

        with patch("app.utils.job_results_store.get_job_results_path", return_value=failing_path):
            result = delete_job_results_from_disk("job_del_fail")
            assert result is False
