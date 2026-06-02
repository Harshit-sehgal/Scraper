"""Unit Tests for Scraper Diagnostics.

Tests ScraperDiagnosticReport and the run_diagnostics function.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.models import FieldType, SchemaField
from app.scraper_diagnostics import ScraperDiagnosticReport, run_diagnostics


class TestScraperDiagnosticReport:
    """Tests for the ScraperDiagnosticReport data class."""

    def test_default_values(self):
        report = ScraperDiagnosticReport("http://example.com")
        assert report.url == "http://example.com"
        assert report.fetch_ms == 0
        assert report.fetch_method == ""
        assert report.dom_nodes == 0
        assert report.anti_bot_score == 0
        assert report.extraction_method == ""
        assert report.selector_success is False
        assert report.memory_hit is False
        assert report.raw_records_count == 0
        assert report.final_records_count == 0
        assert report.record_samples == []
        assert report.errors == []

    def test_to_dict_structure(self):
        report = ScraperDiagnosticReport("http://example.com")
        report.fetch_ms = 150.5
        report.fetch_method = "playwright"
        report.dom_nodes = 500
        report.anti_bot_score = 0.05
        report.extraction_method = "llm"
        report.selector_success = True
        report.memory_hit = True
        report.raw_records_count = 10
        report.final_records_count = 5
        report.record_samples = [{"name": "Item1"}, {"name": "Item2"}]

        d = report.to_dict()
        assert d["url"] == "http://example.com"
        assert d["fetch"]["ms"] == 150.5
        assert d["fetch"]["method"] == "playwright"
        assert d["dom"]["nodes"] == 500
        assert d["dom"]["anti_bot"] == 0.05
        assert d["extraction"]["method"] == "llm"
        assert d["extraction"]["selector_success"] is True
        assert d["extraction"]["memory_hit"] is True
        assert d["results"]["raw_count"] == 10
        assert d["results"]["final_count"] == 5
        assert len(d["results"]["samples"]) == 2
        assert "latency_ms" in d
        assert d["errors"] == []

    def test_to_dict_samples_limited_to_3(self):
        report = ScraperDiagnosticReport("http://example.com")
        report.record_samples = [{"i": i} for i in range(10)]
        d = report.to_dict()
        assert len(d["results"]["samples"]) == 3

    def test_to_dict_includes_errors(self):
        report = ScraperDiagnosticReport("http://example.com")
        report.errors.append("Network timeout")
        report.errors.append("Parse error")
        d = report.to_dict()
        assert d["errors"] == ["Network timeout", "Parse error"]

    def test_to_dict_latency_ms_is_positive(self):
        report = ScraperDiagnosticReport("http://example.com")
        import time

        time.sleep(0.001)
        d = report.to_dict()
        assert d["latency_ms"] > 0


@pytest.mark.asyncio
class TestRunDiagnostics:
    """Tests for the run_diagnostics async function."""

    async def test_success_path(self):
        """Successful extraction returns a populated report."""
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]

        with (
            patch("app.scraper_diagnostics.fetch_page_content") as mock_fetch,
            patch("app.scraper_diagnostics.estimate_dom_nodes", return_value=300) as mock_dom,
            patch("app.scraper_diagnostics.detect_anti_bot", return_value=0.1) as mock_ab,
            patch("app.scraper_diagnostics.get_selector_memory") as mock_mem,
            patch("app.scraper_diagnostics.orchestrate_extraction") as mock_extract,
            patch("app.scraper_diagnostics.process_raw_records") as mock_process,
        ):
            mock_fetch.return_value = ("<html>content</html>", 0.5, "playwright", 0)

            mock_mem_instance = MagicMock()
            mock_mem_instance.get_selectors.return_value = ["sel1"]
            mock_mem.return_value = mock_mem_instance

            mock_extract_result = MagicMock()
            mock_extract_result.method = "llm"
            mock_extract_result.selector_success = True
            mock_extract_result.records = [{"name": "Raw1"}, {"name": "Raw2"}]
            mock_extract.return_value = mock_extract_result

            final_records = [{"name": "Final1"}, {"name": "Final2"}]
            mock_process.return_value = final_records

            report = await run_diagnostics("http://example.com", schema)

            assert report.url == "http://example.com"
            assert report.fetch_method == "playwright"
            assert report.dom_nodes == 300
            assert report.anti_bot_score == 0.1
            assert report.extraction_method == "llm"
            assert report.selector_success is True
            assert report.memory_hit is True
            assert report.raw_records_count == 2
            assert report.final_records_count == 2
            assert report.record_samples == final_records
            assert report.errors == []
            assert report.fetch_ms > 0

            mock_fetch.assert_called_once_with("http://example.com")
            mock_dom.assert_called_once()
            mock_ab.assert_called_once()
            mock_mem_instance.get_selectors.assert_called_once_with("http://example.com")
            mock_extract.assert_called_once()
            mock_process.assert_called_once()

    async def test_error_path_populates_errors(self):
        """When extraction throws, errors list should be populated."""
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]

        with (
            patch("app.scraper_diagnostics.fetch_page_content") as mock_fetch,
            patch("app.scraper_diagnostics.orchestrate_extraction") as mock_extract,
        ):
            mock_fetch.return_value = ("<html>content</html>", 0.5, "httpx", 0)
            mock_extract.side_effect = ValueError("LLM API key missing")

            report = await run_diagnostics("http://example.com", schema)

            assert report.url == "http://example.com"
            assert len(report.errors) == 1
            assert "LLM API key missing" in report.errors[0]
            # Default values preserved on error
            assert report.final_records_count == 0
            assert report.record_samples == []

    async def test_fetch_failure_still_produces_report(self):
        """Even early failures produce a report with error."""
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]

        with patch("app.scraper_diagnostics.fetch_page_content") as mock_fetch:
            mock_fetch.side_effect = RuntimeError("Connection refused")

            report = await run_diagnostics("http://bad-host.com", schema)

            assert len(report.errors) == 1
            assert "Connection refused" in report.errors[0]

    async def test_memory_miss(self):
        """When no selectors in memory, memory_hit is False."""
        schema = [SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)]

        with (
            patch("app.scraper_diagnostics.fetch_page_content") as mock_fetch,
            patch("app.scraper_diagnostics.get_selector_memory") as mock_mem,
            patch("app.scraper_diagnostics.orchestrate_extraction") as mock_extract,
            patch("app.scraper_diagnostics.process_raw_records", return_value=[]),
        ):
            mock_fetch.return_value = ("<html>content</html>", 0.5, "playwright", 0)

            mock_mem_instance = MagicMock()
            mock_mem_instance.get_selectors.return_value = None
            mock_mem.return_value = mock_mem_instance

            mock_extract_result = MagicMock()
            mock_extract_result.records = []
            mock_extract.return_value = mock_extract_result

            report = await run_diagnostics("http://example.com", schema)

            assert report.memory_hit is False
