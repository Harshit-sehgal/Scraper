"""Extraction Screenshot Store — save and retrieve per-extraction page screenshots.

Stores PNG screenshots in ``data/screenshots/`` with job-ID-based filenames.
Provides helpers for saving, retrieving, and listing screenshots.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SCREENSHOTS_DIR = _BACKEND_ROOT / "data" / "screenshots"

# Thread-safe latch for directory creation
_dir_ready = threading.Event()


def _ensure_dir() -> None:
    """Create the screenshots directory if it doesn't exist (once)."""
    if not _dir_ready.is_set():
        _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        _dir_ready.set()


def save_extraction_screenshot(job_id: str, screenshot_bytes: bytes) -> str:
    """Save a PNG screenshot for *job_id* and return the file path.

    If a screenshot already exists for the job it is overwritten.
    """
    _ensure_dir()
    path = _SCREENSHOTS_DIR / f"{job_id}.png"
    # Atomic write: write to temp then replace
    tmp_path = _SCREENSHOTS_DIR / f"{job_id}.png.tmp"
    try:
        tmp_path.write_bytes(screenshot_bytes)
        os.replace(str(tmp_path), str(path))
    except OSError as exc:
        _logger.warning("Failed to save screenshot for job %s: %s", job_id, exc)
        # Clean up temp file if rename failed
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise
    _logger.debug("Saved screenshot for job %s (%d bytes)", job_id, len(screenshot_bytes))
    return str(path)


def get_screenshot_path(job_id: str) -> str | None:
    """Return the path to the screenshot for *job_id*, or ``None`` if not found."""
    path = _SCREENSHOTS_DIR / f"{job_id}.png"
    return str(path) if path.exists() else None


def list_screenshots() -> list[str]:
    """Return a list of job IDs that have saved screenshots."""
    if not _SCREENSHOTS_DIR.exists():
        return []
    return sorted(p.stem for p in _SCREENSHOTS_DIR.iterdir() if p.suffix == ".png" and p.is_file())


def delete_screenshot(job_id: str) -> bool:
    """Delete the screenshot for *job_id*. Returns ``True`` if it existed."""
    path = _SCREENSHOTS_DIR / f"{job_id}.png"
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


__all__ = [
    "delete_screenshot",
    "get_screenshot_path",
    "list_screenshots",
    "save_extraction_screenshot",
]
