"""Unit tests for extraction_screenshot_store.

Covers saving, retrieving, listing, and deleting screenshots
using a temporary directory so no real data directory is touched.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from app import extraction_screenshot_store as ess

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _tmp_screenshots_dir(tmp_path: Path) -> None:
    """Redirect the screenshots directory to a temp dir and reset the latch."""
    target = tmp_path / "screenshots"
    target.mkdir(parents=True, exist_ok=True)
    # Reset the one-shot latch so _ensure_dir re-runs
    ess._dir_ready.clear()
    with patch.object(ess, "_SCREENSHOTS_DIR", target):
        yield
    # Cleanup: reset latch again
    ess._dir_ready.clear()


# ---------------------------------------------------------------------------
# save_extraction_screenshot
# ---------------------------------------------------------------------------


class TestSaveExtractionScreenshot:
    """save_extraction_screenshot creates a PNG file."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Saving a screenshot creates a .png file on disk."""
        data = b"\x89PNG\r\n\x1a\n"  # minimal PNG header
        returned_path = ess.save_extraction_screenshot("job-save", data)
        expected = str(tmp_path / "screenshots" / "job-save.png")
        assert returned_path == expected
        assert Path(returned_path).exists()
        assert Path(returned_path).read_bytes() == data

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """Saving for an existing job_id overwrites the previous file."""
        ess.save_extraction_screenshot("job-ow", b"old")
        ess.save_extraction_screenshot("job-ow", b"new")
        path = tmp_path / "screenshots" / "job-ow.png"
        assert path.read_bytes() == b"new"

    def test_raises_on_write_failure(self) -> None:
        """An OSError during write is re-raised after cleanup."""
        _DISK_FULL = OSError("disk full")
        with patch.object(ess.Path, "write_bytes", side_effect=_DISK_FULL):
            with pytest.raises(OSError, match="disk full"):
                ess.save_extraction_screenshot("job-fail", b"data")


# ---------------------------------------------------------------------------
# get_screenshot_path
# ---------------------------------------------------------------------------


class TestGetScreenshotPath:
    """get_screenshot_path returns a path or None."""

    def test_returns_none_for_missing(self) -> None:
        """A non-existent screenshot yields None."""
        assert ess.get_screenshot_path("no-such-job") is None

    def test_returns_path_for_existing(self, tmp_path: Path) -> None:
        """An existing screenshot returns its file path."""
        ess.save_extraction_screenshot("job-exist", b"\x89PNG")
        result = ess.get_screenshot_path("job-exist")
        assert result is not None
        assert result.endswith("job-exist.png")


# ---------------------------------------------------------------------------
# list_screenshots
# ---------------------------------------------------------------------------


class TestListScreenshots:
    """list_screenshots returns sorted job IDs with screenshots."""

    def test_returns_job_ids(self, tmp_path: Path) -> None:
        """Saved job IDs appear in the listing."""
        ess.save_extraction_screenshot("job-b", b"b")
        ess.save_extraction_screenshot("job-a", b"a")
        ids = ess.list_screenshots()
        assert ids == ["job-a", "job-b"]  # sorted

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        """When the directory doesn't exist, an empty list is returned."""
        # Point to a non-existent dir
        with patch.object(ess, "_SCREENSHOTS_DIR", tmp_path / "no-dir"):
            ess._dir_ready.clear()
            assert ess.list_screenshots() == []

    def test_excludes_non_png_files(self, tmp_path: Path) -> None:
        """Non-.png files are not included in the listing."""
        target = tmp_path / "screenshots"
        (target / "notes.txt").write_text("ignore me")
        ids = ess.list_screenshots()
        assert ids == []


# ---------------------------------------------------------------------------
# delete_screenshot
# ---------------------------------------------------------------------------


class TestDeleteScreenshot:
    """delete_screenshot removes the screenshot file."""

    def test_removes_existing_file(self, tmp_path: Path) -> None:
        """Deleting an existing screenshot returns True and the file is gone."""
        ess.save_extraction_screenshot("job-del", b"del")
        result = ess.delete_screenshot("job-del")
        assert result is True
        assert ess.get_screenshot_path("job-del") is None

    def test_nonexistent_returns_true(self) -> None:
        """Deleting a non-existent screenshot still returns True (missing_ok)."""
        result = ess.delete_screenshot("no-such-job")
        assert result is True

    def test_oserror_returns_false(self, tmp_path: Path) -> None:
        """If unlink raises OSError, False is returned."""
        ess.save_extraction_screenshot("job-err", b"data")
        _PERM_DENIED = OSError("permission denied")
        with patch.object(ess.Path, "unlink", side_effect=_PERM_DENIED):
            result = ess.delete_screenshot("job-err")
        assert result is False
