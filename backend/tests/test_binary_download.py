"""Tests for binary download support in extraction.

Roadmap: Feat 5 — scrape_url(extract_binary=True) that saves PDF, ZIP, image files
to storage and returns a download URL in the result metadata.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.binary_handler import (
    _binary_store,
    _binary_store_lock,
    _detect_content_type_from_url,
    _get_binaries_dir,
    _get_extension_for_content_type,
    download_binary,
    get_binary_metadata,
    is_binary_content_type,
)
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestContentTypeDetection:
    """Unit tests for binary content-type detection."""

    def test_is_binary_content_type_pdf(self) -> None:
        assert is_binary_content_type("application/pdf") is True

    def test_is_binary_content_type_zip(self) -> None:
        assert is_binary_content_type("application/zip") is True

    def test_is_binary_content_type_png(self) -> None:
        assert is_binary_content_type("image/png") is True

    def test_is_binary_content_type_html(self) -> None:
        assert is_binary_content_type("text/html") is False

    def test_is_binary_content_type_none(self) -> None:
        assert is_binary_content_type(None) is False

    def test_is_binary_content_type_empty(self) -> None:
        assert is_binary_content_type("") is False

    def test_is_binary_content_type_office_doc(self) -> None:
        assert is_binary_content_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document") is True

    def test_is_binary_content_type_octet_stream(self) -> None:
        assert is_binary_content_type("application/octet-stream") is True

    def test_is_binary_content_type_audio(self) -> None:
        assert is_binary_content_type("audio/mpeg") is True

    def test_detect_content_type_from_url_pdf(self) -> None:
        assert _detect_content_type_from_url("https://example.com/report.pdf") == "application/pdf"

    def test_detect_content_type_from_url_zip(self) -> None:
        assert _detect_content_type_from_url("https://example.com/archive.zip") == "application/zip"

    def test_detect_content_type_from_url_jpg(self) -> None:
        assert _detect_content_type_from_url("https://example.com/photo.jpg") == "image/jpeg"

    def test_detect_content_type_from_url_html_page(self) -> None:
        assert _detect_content_type_from_url("https://example.com/page") is None

    def test_detect_content_type_from_url_unknown(self) -> None:
        assert _detect_content_type_from_url("https://example.com/data.bin") is None

    def test_get_extension_for_content_type_pdf(self) -> None:
        assert _get_extension_for_content_type("application/pdf") == ".pdf"

    def test_get_extension_for_content_type_png(self) -> None:
        assert _get_extension_for_content_type("image/png") == ".png"

    def test_get_extension_for_content_type_unknown(self) -> None:
        ext = _get_extension_for_content_type("application/x-custom")
        assert ext == ".bin"

    def test_get_extension_for_content_type_image_generic(self) -> None:
        ext = _get_extension_for_content_type("image/tiff")
        assert ext in {".img", ".tiff"}


class TestBinaryDownloadUnit:
    """Unit tests for the binary download handler with mocked HTTP."""

    @pytest.fixture(autouse=True)
    def _reset_store(self) -> None:
        """Clear the in-memory binary store before each test."""
        with _binary_store_lock:
            _binary_store.clear()

    @pytest.fixture(autouse=True)
    def _temp_binaries_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Redirect the binaries directory to a temp dir."""
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))

    @pytest.mark.asyncio
    async def test_download_binary_saves_file(self) -> None:
        """Verify that downloading a binary saves content to disk."""
        mock_content = b"%PDF-1.4 fake pdf content for testing purposes"

        mock_response = MagicMock()
        mock_response.content = mock_content
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.binary_handler.get_safe_async_client", return_value=mock_client):
            meta = await download_binary("https://example.com/report.pdf")

        assert meta["content_type"] == "application/pdf"
        assert meta["file_size"] == len(mock_content)
        assert meta["download_url"].startswith("/api/download/")
        assert meta["download_url"].endswith(".pdf")
        assert meta["original_url"] == "https://example.com/report.pdf"

        # Verify the file was written to disk
        binaries_dir = Path(_get_binaries_dir())
        saved_file = binaries_dir / meta["filename"]
        assert saved_file.exists()
        assert saved_file.read_bytes() == mock_content

    @pytest.mark.asyncio
    async def test_download_binary_stores_metadata(self) -> None:
        """Verify metadata is stored in the in-memory store."""
        mock_response = MagicMock()
        mock_response.content = b"fake binary content"
        mock_response.headers = {"content-type": "application/zip"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.binary_handler.get_safe_async_client", return_value=mock_client):
            meta = await download_binary("https://example.com/data.zip")

        retrieved = get_binary_metadata(meta["filename"])
        assert retrieved is not None
        assert retrieved["content_type"] == "application/zip"
        assert retrieved["file_size"] == len(mock_response.content)

    @pytest.mark.asyncio
    async def test_download_binary_rejects_non_binary_url(self) -> None:
        """A URL without binary extension should still download if content-type indicates binary."""
        mock_response = MagicMock()
        mock_response.content = b"some binary data"
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.binary_handler.get_safe_async_client", return_value=mock_client):
            meta = await download_binary("https://example.com/unknown.xyz")

        assert meta["content_type"] == "application/octet-stream"
        assert meta["file_size"] == 16

    @pytest.mark.asyncio
    async def test_download_binary_rejects_html_response(self) -> None:
        """Text/html responses are not saved through the binary path."""
        mock_response = MagicMock()
        mock_response.content = b"<html><body>not a binary</body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("app.binary_handler.get_safe_async_client", return_value=mock_client),
            pytest.raises(ValueError, match="did not return binary content"),
        ):
            await download_binary("https://example.com/report.pdf")

    @pytest.mark.asyncio
    async def test_binary_file_is_served_via_get_binary_file_path(self) -> None:
        """Verify the binary file can be resolved on disk."""
        mock_response = MagicMock()
        mock_response.content = b"test content"
        mock_response.headers = {"content-type": "image/png"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        from app.binary_handler import get_binary_file_path

        with patch("app.binary_handler.get_safe_async_client", return_value=mock_client):
            meta = await download_binary("https://example.com/icon.png")

        path = get_binary_file_path(meta["filename"])
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == b"test content"

    @pytest.mark.asyncio
    async def test_get_binary_file_path_returns_none_for_missing(self) -> None:
        """Missing files return None."""
        from app.binary_handler import get_binary_file_path

        assert get_binary_file_path("nonexistent.pdf") is None


class TestScrapeUrlBinaryIntegration:
    """Integration-level tests — scrape_url with extract_binary=True,
    mocking the HTTP layer to avoid real network calls."""

    @pytest.fixture(autouse=True)
    def _temp_binaries_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DATAFORGE_STATE_DIR", str(tmp_path))

    @pytest.mark.asyncio
    async def test_extract_binary_true_with_pdf_url(self) -> None:
        """scrape_url with extract_binary=True on a PDF-like URL saves binary."""
        mock_response = MagicMock()
        mock_response.content = b"%PDF-1.4 sample pdf bytes"
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("app.binary_handler.get_safe_async_client", return_value=mock_client),
        ):
            result = await scrape_url(
                "https://example.com/sample.pdf",
                [],
                extract_binary=True,
            )

        assert isinstance(result, list)
        assert len(result) == 1
        record = result[0]
        assert "_binary_file_url" in record
        assert record["_binary_file_url"].startswith("/api/download/")
        assert record["_binary_content_type"] == "application/pdf"
        assert record["_binary_file_size"] == len(mock_response.content)
        assert record["source_url"] == "https://example.com/sample.pdf"

    @pytest.mark.asyncio
    async def test_extract_binary_false_returns_normal_result(self) -> None:
        """When extract_binary=False, no binary metadata is present."""
        from app.scraper import ScrapeAttemptResult

        mock_result = ScrapeAttemptResult(
            [{"source_url": "https://example.com/document.pdf", "text": "extracted text"}],
            html=None,
            final_url="https://example.com/document.pdf",
        )

        with (
            patch("app.binary_handler.download_binary") as mock_download,
            patch("app.scraper._check_crawl_policy", new=AsyncMock(return_value=mock_result)),
        ):
            result = await scrape_url(
                "https://example.com/document.pdf",
                [SchemaField(name="content", field_type=FieldType.STRING, required=False)],
                extract_binary=False,
            )

        mock_download.assert_not_called()
        assert isinstance(result, list)
        assert len(result) >= 1
        record = result[0]
        assert "_binary_file_url" not in record
        assert "_binary_content_type" not in record

    @pytest.mark.asyncio
    async def test_extract_binary_default_false(self) -> None:
        """Default value of extract_binary is False (backward-compatible)."""
        from app.scraper import ScrapeAttemptResult

        mock_result = ScrapeAttemptResult(
            [{"source_url": "https://example.com/report.pdf", "text": "test"}],
            html=None,
            final_url="https://example.com/report.pdf",
        )

        with (
            patch("app.binary_handler.download_binary") as mock_download,
            patch("app.scraper._check_crawl_policy", new=AsyncMock(return_value=mock_result)),
        ):
            result = await scrape_url("https://example.com/report.pdf", [])

        mock_download.assert_not_called()
        assert isinstance(result, list)
        assert len(result) >= 1
        record = result[0]
        # No binary metadata when extract_binary is not set (default False)
        assert "_binary_file_url" not in record
        assert "_binary_content_type" not in record

    @pytest.mark.asyncio
    async def test_extract_binary_with_image_url(self) -> None:
        """Image URLs are handled correctly with extract_binary=True."""
        mock_response = MagicMock()
        mock_response.content = b"\x89PNG\r\n\x1a\nbinary png content"
        mock_response.headers = {"content-type": "image/png"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("app.binary_handler.get_safe_async_client", return_value=mock_client),
        ):
            result = await scrape_url(
                "https://example.com/photo.jpg",
                [],
                extract_binary=True,
            )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["_binary_content_type"] == "image/png"
        assert result[0]["_binary_file_size"] == len(mock_response.content)

    @pytest.mark.asyncio
    async def test_extract_binary_zip_file(self) -> None:
        """ZIP files are handled correctly with extract_binary=True."""
        mock_response = MagicMock()
        mock_response.content = b"PK\x03\x04fake zip content"
        mock_response.headers = {"content-type": "application/zip"}
        mock_response.status_code = 200
        mock_response.aclose = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("app.binary_handler.get_safe_async_client", return_value=mock_client),
        ):
            result = await scrape_url(
                "https://example.com/archive.zip",
                [],
                extract_binary=True,
            )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["_binary_content_type"] == "application/zip"
        assert result[0]["_binary_filename"].endswith(".zip")

    @pytest.mark.asyncio
    async def test_extract_binary_unknown_extension_uses_normal_pipeline(self) -> None:
        """Unknown extensions do not force a binary download without a URL clue."""
        from app.scraper import ScrapeAttemptResult

        mock_result = ScrapeAttemptResult(
            [{"source_url": "https://example.com/data.bin", "text": "normal path"}],
            html="<html></html>",
            final_url="https://example.com/data.bin",
        )

        with (
            patch("app.binary_handler.download_binary") as mock_download,
            patch("app.scraper._check_crawl_policy", new=AsyncMock(return_value=mock_result)),
        ):
            result = await scrape_url("https://example.com/data.bin", [], extract_binary=True)

        mock_download.assert_not_called()
        assert result[0]["text"] == "normal path"
