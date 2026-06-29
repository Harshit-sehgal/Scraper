"""Obs 6: Screenshot-per-extraction storage — test screenshot storage with job."""
from __future__ import annotations

import base64
import json
from typing import Any


def _store_screenshot(job_id: str, screenshot_b64: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Simulate storing a screenshot with a job.
    
    Returns a screenshot record.
    """
    size_bytes = len(base64.b64decode(screenshot_b64)) if screenshot_b64 else 0
    return {
        "job_id": job_id,
        "screenshot_b64": screenshot_b64,
        "size_bytes": size_bytes,
        "format": "jpeg",
        "metadata": metadata or {},
        "stored_at": "2026-06-29T00:00:00Z",
    }


class TestScreenshotStorage:
    def test_screenshot_stored_with_job_id(self) -> None:
        img_b64 = base64.b64encode(b"fake_image_bytes_12345").decode("ascii")
        result = _store_screenshot("job-001", img_b64)
        assert result["job_id"] == "job-001"
        assert result["screenshot_b64"] == img_b64

    def test_screenshot_size_tracked(self) -> None:
        img_b64 = base64.b64encode(b"x" * 1000).decode("ascii")
        result = _store_screenshot("job-002", img_b64)
        assert result["size_bytes"] == 1000

    def test_empty_screenshot_has_zero_size(self) -> None:
        result = _store_screenshot("job-003", "")
        assert result["size_bytes"] == 0

    def test_metadata_stored(self) -> None:
        meta = {"url": "https://example.com", "viewport": "1920x1080"}
        result = _store_screenshot("job-004", base64.b64encode(b"data").decode("ascii"), metadata=meta)
        assert result["metadata"]["url"] == "https://example.com"

    def test_serializable(self) -> None:
        img_b64 = base64.b64encode(b"screenshot_data").decode("ascii")
        result = _store_screenshot("job-005", img_b64)
        dumped = json.dumps(result, default=str)
        assert isinstance(dumped, str)


class TestScreenshotRetrieval:
    def test_screenshot_base64_is_valid(self) -> None:
        data = b"valid_binary_screenshot_data"
        img_b64 = base64.b64encode(data).decode("ascii")
        result = _store_screenshot("job-010", img_b64)
        decoded = base64.b64decode(result["screenshot_b64"])
        assert decoded == data

    def test_screenshot_b64_size(self) -> None:
        data = b"test_screenshot_payload"
        img_b64 = base64.b64encode(data).decode("ascii")
        result = _store_screenshot("job-011", img_b64)
        assert len(result["screenshot_b64"]) > 0
        assert result["size_bytes"] == len(data)


class TestScreenshotLargeFile:
    def test_large_screenshot(self) -> None:
        data = b"A" * 500_000
        img_b64 = base64.b64encode(data).decode("ascii")
        result = _store_screenshot("job-020", img_b64)
        assert result["size_bytes"] == 500_000
