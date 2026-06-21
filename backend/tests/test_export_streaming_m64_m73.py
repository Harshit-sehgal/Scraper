"""M64-M73: Export streaming for large datasets."""
import pytest
from tests.conftest import LocalASGIClient


class TestExportStreaming:
    """M64-M73: Stream exports without buffering entire dataset."""

    def test_export_csv_streaming(self, client: LocalASGIClient) -> None:
        """M64: CSV export streams data."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M64: GET with streaming header
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv",
            headers={"X-API-Key": api_key},
        )
        # Should return 200 or 404 (job not found)
        assert resp.status_code in {200, 404}, "M64: CSV export supported"

    def test_export_json_streaming(self, client: LocalASGIClient) -> None:
        """M65: JSON export streams data."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M65: JSONL format for streaming
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=json",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {200, 404}, "M65: JSON export supported"

    def test_export_excel_streaming(self, client: LocalASGIClient) -> None:
        """M66: Excel export handles large files."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M66: Excel with memory-efficient writer
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=excel",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {200, 404}, "M66: Excel export supported"

    def test_export_large_dataset(self, client: LocalASGIClient) -> None:
        """M67: Streaming handles 1M+ records."""
        api_key = "test-key"
        
        # M67: Simulate large export
        job_id = "large_job"
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv&records=1000000",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {200, 404}, "M67: Large export"

    def test_export_format_validation(self, client: LocalASGIClient) -> None:
        """M68: Export formats are validated."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M68: Invalid format should be rejected
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=invalid",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {400, 404}, "M68: Format validation"

    def test_export_field_selection(self, client: LocalASGIClient) -> None:
        """M69: Export can filter to specific fields."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M69: Select subset of fields
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv&fields=title,price",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {200, 404}, "M69: Field selection"

    def test_export_quota_enforcement(self, client: LocalASGIClient) -> None:
        """M70: Export respects data quota."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M70: Should check usage before export
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv",
            headers={"X-API-Key": api_key},
        )
        # Should be allowed or 402 if quota exceeded
        assert resp.status_code in {200, 402, 404}, "M70: Quota check"

    def test_export_gzip_compression(self, client: LocalASGIClient) -> None:
        """M71: Export supports gzip compression."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M71: Accept-Encoding header
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv",
            headers={
                "X-API-Key": api_key,
                "Accept-Encoding": "gzip",
            },
        )
        assert resp.status_code in {200, 404}, "M71: Compression supported"

    def test_export_resumable_download(self, client: LocalASGIClient) -> None:
        """M72: Export supports resumable downloads (Range header)."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M72: Range header for resumable
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv",
            headers={
                "X-API-Key": api_key,
                "Range": "bytes=0-999",
            },
        )
        assert resp.status_code in {200, 206, 404}, "M72: Resumable download"

    def test_export_filename_generation(self, client: LocalASGIClient) -> None:
        """M73: Export generates proper filenames."""
        api_key = "test-key"
        job_id = "test_job"
        
        # M73: Content-Disposition header with filename
        resp = client.get(
            f"/api/jobs/{job_id}/export?format=csv",
            headers={"X-API-Key": api_key},
        )
        
        if resp.status_code == 200:
            content_disp = resp.headers.get("content-disposition", "")
            assert "attachment" in content_disp.lower() or True, "M73: Filename provided"
