from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from app.utils.job_results_store import (
    _resolve_results_path,
)


@pytest.fixture
def mock_state_path(tmp_path: Path) -> Iterator[Path]:
    """Fixture: create a temporary state directory and mock get_state_file_path."""
    state_file = tmp_path / "state" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{}")
    with patch("app.state_store.get_state_file_path", return_value=state_file):
        yield state_file


def test_resolve_results_path_rejects_outside_results_dir(mock_state_path: Path) -> None:
    # 1. Reject paths outside results dir
    with pytest.raises(ValueError, match="Rejected results path outside managed directory"):
        _resolve_results_path("job-123", "/etc/passwd")

    with pytest.raises(ValueError, match="Rejected results path outside managed directory"):
        _resolve_results_path("job-123", "../outside.jsonl.gz")


def test_resolve_results_path_rejects_mismatched_filename(mock_state_path: Path) -> None:
    # 2. Reject paths inside directory but with unexpected prefix
    # Path is inside the directory but name does not start with results_job-123
    results_dir = mock_state_path.parent / "results"
    outside_file = results_dir / "results_job-other.jsonl.gz"

    with pytest.raises(ValueError, match="Rejected results path with unexpected filename"):
        _resolve_results_path("job-123", str(outside_file))


def test_resolve_results_path_accepts_valid_path(mock_state_path: Path) -> None:
    # 3. Accept valid paths
    results_dir = mock_state_path.parent / "results"
    valid_file = results_dir / "results_job-123.jsonl.gz"

    resolved = _resolve_results_path("job-123", str(valid_file))
    assert resolved.resolve() == valid_file.resolve()
