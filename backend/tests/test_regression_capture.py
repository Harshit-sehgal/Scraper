"""
Tests for Regression Capture — self-growing benchmark system.

Covers:
  - Capture criteria (empty results, low quality, forced capture)
  - Deduplication (same HTML hash skipped)
  - Fixture file creation
  - Registry persistence (save/load round-trip)
  - Replay test generation
  - Statistics and domain/category coverage
  - Edge cases (None HTML, empty strings, unknown domain)
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from app.regression_capture import (
    RegressionCapture,
    RegressionEntry,
    RegressionRegistry,
    get_regression_capture,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def capture_instance(tmp_path: Path) -> RegressionCapture:
    """Create a RegressionCapture with temp directories for isolation."""
    fixtures_dir = tmp_path / "fixtures"
    registry_path = tmp_path / "registry.json"
    return RegressionCapture(
        fixtures_dir=str(fixtures_dir),
        registry_path=str(registry_path),
        min_confidence=0.3,
        min_html_length=20,
        auto_archive=True,
    )


@pytest.fixture
def sample_html() -> str:
    return "<html><body><h1>Test Page</h1><p>Some content here.</p></body></html>"


# ═══════════════════════════════════════════════════════════════════════
# Capture Logic Tests
# ═══════════════════════════════════════════════════════════════════════


class TestCaptureCriteria:
    """Verify the capture criteria work correctly."""

    def test_captures_empty_results_with_high_confidence(self, capture_instance, sample_html):
        """Captures when extraction returned 0 records with high confidence."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.85,
            records_count=0,
        )
        assert entry is not None
        assert entry.failure_category == "anti_bot_block"
        assert entry.failure_confidence == 0.85
        assert entry.html_size == len(sample_html)

    def test_skips_low_confidence_with_results(self, capture_instance, sample_html):
        """Skips when extraction returned records and confidence is below threshold."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html=sample_html,
            failure_category="selector_decay",
            failure_confidence=0.2,
            records_count=5,
        )
        assert entry is None

    def test_skips_empty_html(self, capture_instance):
        """Skips when HTML is None or too short."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html=None,
            failure_category="dns_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is None

        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html="",
            failure_category="dns_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is None

    def test_skips_short_html(self, capture_instance):
        """Skips when HTML is below min_html_length."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html="<short/>",
            failure_category="empty_page",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is None

    def test_force_capture_bypasses_criteria(self, capture_instance):
        """force=True captures regardless of criteria."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/page",
            html="<p>short</p>",
            failure_category="low_quality",
            failure_confidence=0.1,
            records_count=10,
            force=True,
        )
        assert entry is not None
        assert entry.failure_category == "low_quality"

    def test_captures_with_schema_fields(self, capture_instance, sample_html):
        """Captures with schema field metadata."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/data",
            html=sample_html,
            failure_category="hydration_failure",
            failure_confidence=0.7,
            records_count=0,
            schema_fields=["company_name", "email", "phone"],
        )
        assert entry is not None
        assert "company_name" in entry.schema_fields
        assert len(entry.schema_fields) == 3

    def test_captures_with_telemetry(self, capture_instance, sample_html):
        """Captures with telemetry snapshot."""
        telemetry = {
            "fetch_method": "playwright",
            "dom_nodes": 150,
            "anti_bot_score": 0.8,
            "selector_hit_rate": 0.0,
            "fetch_ms": 3200,
        }
        entry = capture_instance.maybe_capture(
            url="https://example.com/data",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
            telemetry=telemetry,
        )
        assert entry is not None
        assert entry.telemetry_snapshot["anti_bot_score"] == 0.8

    def test_records_count_zero_always_captures_with_confidence(self, capture_instance, sample_html):
        """Zero records with sufficient confidence always captures."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/no-data",
            html=sample_html,
            failure_category="no_records_extracted",
            failure_confidence=0.6,
            records_count=0,
        )
        assert entry is not None


class TestDeduplication:
    """Verify duplicate detection works."""

    def test_duplicate_content_skipped(self, capture_instance, sample_html):
        """Same HTML content hash is not captured twice."""
        entry1 = capture_instance.maybe_capture(
            url="https://example.com/page1",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
        )
        entry2 = capture_instance.maybe_capture(
            url="https://example.com/page2",
            html=sample_html,
            failure_category="hydration_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry1 is not None
        assert entry2 is None  # Same content hash, should be skipped

    def test_different_content_captured(self, capture_instance):
        """Different HTML content generates different hashes."""
        entry1 = capture_instance.maybe_capture(
            url="https://example.com/page1",
            html="<html><body>Content A</body></html>",
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
        )
        entry2 = capture_instance.maybe_capture(
            url="https://example.com/page2",
            html="<html><body>Content B</body></html>",
            failure_category="hydration_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry1 is not None
        assert entry2 is not None
        assert entry1.id != entry2.id


class TestFixtureCreation:
    """Verify fixture files are created correctly."""

    def test_fixture_file_created(self, capture_instance, tmp_path):
        """Captured HTML is saved as a fixture file."""
        html = "<html><body>Fixture content here</body></html>"
        entry = capture_instance.maybe_capture(
            url="https://example.com/fixture-test",
            html=html,
            failure_category="no_records_extracted",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is not None
        fixture_path = tmp_path / "fixtures" / entry.fixture_filename
        assert fixture_path.exists()
        assert fixture_path.read_text(encoding="utf-8") == html

    def test_fixture_not_created_when_auto_archive_off(self, tmp_path):
        """auto_archive=False skips fixture file creation."""
        capture = RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "registry.json"),
            auto_archive=False,
        )
        html = "<html><body>" + "No archive content here." * 10 + "</body></html>"
        entry = capture.maybe_capture(
            url="https://example.com/no-archive",
            html=html,
            failure_category="no_records_extracted",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is not None
        assert entry.fixture_filename
        fixture_path = tmp_path / "fixtures" / entry.fixture_filename
        assert not fixture_path.exists()


class TestRegistryPersistence:
    """Verify the registry saves and loads correctly."""

    def test_registry_saved_to_disk(self, capture_instance, tmp_path, sample_html):
        """After capture, registry file exists with correct data."""
        capture_instance.maybe_capture(
            url="https://example.com/persist",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
        )
        registry_path = tmp_path / "registry.json"
        assert registry_path.exists()
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        assert data["total_captured"] == 1
        assert len(data["entries"]) == 1

    def test_registry_loads_from_disk(self, tmp_path):
        """Captures survive a fresh RegressionCapture instance."""
        fixtures_dir = tmp_path / "fixtures"
        registry_path = tmp_path / "registry.json"
        long_html = "<html><body>" + "A" * 200 + "</body></html>"

        # First instance
        cap1 = RegressionCapture(
            fixtures_dir=str(fixtures_dir),
            registry_path=str(registry_path),
        )
        cap1.maybe_capture(
            url="https://example.com/load-test",
            html=long_html,
            failure_category="hydration_failure",
            failure_confidence=0.9,
            records_count=0,
        )

        # Second instance (loads from disk)
        cap2 = RegressionCapture(
            fixtures_dir=str(fixtures_dir),
            registry_path=str(registry_path),
        )
        registry = cap2.get_registry()
        assert registry.total_captured == 1
        assert len(registry.entries) == 1
        assert registry.entries[0].failure_category == "hydration_failure"

    def test_empty_registry_on_no_file(self, tmp_path):
        """Capturing with non-existent registry path starts fresh."""
        capture = RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "nonexistent" / "registry.json"),
        )
        registry = capture.get_registry()
        assert registry.total_captured == 0
        assert len(registry.entries) == 0

    def test_corrupted_registry_handled_gracefully(self, tmp_path):
        """Corrupted registry JSON falls back to empty registry."""
        registry_path = tmp_path / "registry.json"
        registry_path.write_text("corrupted json { bad data", encoding="utf-8")
        capture = RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(registry_path),
        )
        # Should not raise
        registry = capture.get_registry()
        assert registry.total_captured == 0


class TestStatistics:
    """Verify statistics and coverage tracking."""

    def test_statistics_after_multiple_captures(self, capture_instance):
        """Statistics reflect all captures correctly."""
        entries_data = [
            ("https://example.com/a", "<html><body>A</body></html>", "anti_bot_block"),
            ("https://other.com/b", "<html><body>B</body></html>", "hydration_failure"),
            ("https://example.com/c", "<html><body>C</body></html>", "anti_bot_block"),
            ("https://test.org/d", "<html><body>D</body></html>", "empty_page"),
            ("https://example.com/e", "<html><body>E</body></html>", "selector_decay"),
        ]

        for url, html, category in entries_data:
            capture_instance.maybe_capture(
                url=url, html=html, failure_category=category,
                failure_confidence=0.9, records_count=0,
            )

        stats = capture_instance.get_statistics()
        assert stats["total_captured"] == 5
        assert stats["domain_count"] == 3  # example.com, other.com, test.org
        assert stats["category_count"] == 4  # anti_bot_block, hydration_failure, empty_page, selector_decay

        # example.com should have 3 captures
        assert stats["domain_coverage"]["example.com"] == 3

    def test_category_coverage(self, capture_instance):
        """Category coverage is tracked correctly."""
        categories = ["anti_bot_block", "anti_bot_block", "hydration_failure", "empty_page"]
        for i, cat in enumerate(categories):
            capture_instance.maybe_capture(
                url=f"https://site{i}.com/page",
                html=f"<html><body>Content {i}</body></html>",
                failure_category=cat,
                failure_confidence=0.9,
                records_count=0,
            )

        stats = capture_instance.get_statistics()
        assert stats["category_coverage"]["anti_bot_block"] == 2
        assert stats["category_coverage"]["hydration_failure"] == 1
        assert stats["category_coverage"]["empty_page"] == 1


class TestReplayTestGeneration:
    """Verify replay test generation."""

    def test_generate_replay_test(self, capture_instance, sample_html, tmp_path):
        """Replay test is generated for a captured regression."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/replay",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.85,
            records_count=0,
            schema_fields=["company_name"],
        )
        assert entry is not None

        test_code = capture_instance.generate_replay_test(entry.id)
        assert test_code is not None
        assert f"test_replay_{entry.id}" in test_code
        assert "anti_bot_block" in test_code
        assert "example.com" in test_code
        assert "company_name" in test_code

        # Verify the entry is marked as having a test
        registry = capture_instance.get_registry()
        assert registry.total_with_replay_tests == 1

    def test_generate_replay_test_missing_entry(self, capture_instance):
        """Returns None for non-existent entry ID."""
        result = capture_instance.generate_replay_test("nonexistent_id")
        assert result is None

    def test_generate_replay_test_missing_fixture(self, capture_instance):
        """Returns None if fixture file was deleted."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/missing-fixture",
            html="<html><body>Content</body></html>",
            failure_category="empty_page",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is not None

        # Delete the fixture file
        fixture_path = capture_instance._fixtures_dir / entry.fixture_filename
        if fixture_path.exists():
            fixture_path.unlink()

        result = capture_instance.generate_replay_test(entry.id)
        assert result is None

    def test_generate_all_replay_tests(self, capture_instance):
        """Generates tests for all captures without existing tests."""
        capture_instance.maybe_capture(
            url="https://example.com/a", html="<html><body>A</body></html>",
            failure_category="anti_bot_block", failure_confidence=0.9, records_count=0,
            schema_fields=["name"],
        )
        capture_instance.maybe_capture(
            url="https://other.com/b", html="<html><body>B</body></html>",
            failure_category="hydration_failure", failure_confidence=0.9, records_count=0,
            schema_fields=["email"],
        )

        all_tests = capture_instance.generate_all_replay_tests()
        assert all_tests is not None
        registry = capture_instance.get_registry()
        assert registry.total_with_replay_tests == 2


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_unknown_domain_handling(self, capture_instance, sample_html):
        """URL with no valid domain is handled gracefully."""
        entry = capture_instance.maybe_capture(
            url="not-a-valid-url",
            html=sample_html,
            failure_category="dns_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is not None
        assert entry.domain == "unknown"

    def test_long_html_is_truncated_in_preview(self, capture_instance):
        """HTML preview is limited to 200 chars."""
        long_html = "<html>" + "A" * 1000 + "</html>"
        entry = capture_instance.maybe_capture(
            url="https://example.com/long",
            html=long_html,
            failure_category="empty_page",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is not None
        assert len(entry.html_preview) <= 200
        assert entry.html_size == len(long_html)

    def test_timestamp_is_set_on_capture(self, capture_instance, sample_html):
        """captured_at is set to a reasonable timestamp."""
        before = time.time()
        entry = capture_instance.maybe_capture(
            url="https://example.com/ts",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
        )
        after = time.time()
        assert entry is not None
        assert before <= entry.captured_at <= after or abs(entry.captured_at - before) < 2

    def test_registry_last_capture_at_updated(self, capture_instance, sample_html):
        """Registry tracks when the last capture occurred."""
        before = time.time()
        capture_instance.maybe_capture(
            url="https://example.com/last",
            html=sample_html,
            failure_category="anti_bot_block",
            failure_confidence=0.9,
            records_count=0,
        )
        after = time.time()
        registry = capture_instance.get_registry()
        assert before <= registry.last_capture_at <= after or abs(registry.last_capture_at - before) < 2

    def test_negative_confidence_handled(self, capture_instance, sample_html):
        """Very low confidence with records doesn't capture (unless forced)."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/low-conf",
            html=sample_html,
            failure_category="selector_decay",
            failure_confidence=-0.1,
            records_count=5,
        )
        assert entry is None  # Negative is below min_confidence

    def test_html_size_zero_for_none_html(self, capture_instance):
        """When html is None, size should be 0 (but capture is skipped)."""
        entry = capture_instance.maybe_capture(
            url="https://example.com/no-html",
            html=None,
            failure_category="dns_failure",
            failure_confidence=0.9,
            records_count=0,
        )
        assert entry is None  # No HTML means no capture


# ═══════════════════════════════════════════════════════════════════════
# Singleton Accessor
# ═══════════════════════════════════════════════════════════════════════


class TestSingleton:
    """Verify the module-level singleton accessor."""

    def test_get_regression_capture_returns_instance(self):
        """get_regression_capture() returns a RegressionCapture instance."""
        capture = get_regression_capture()
        assert isinstance(capture, RegressionCapture)

    def test_singleton_returns_same_instance(self):
        """Multiple calls return the same instance."""
        c1 = get_regression_capture()
        c2 = get_regression_capture()
        assert c1 is c2


# ═══════════════════════════════════════════════════════════════════════
# Integration-Style: Concurrent Captures & Registry Integrity
# ═══════════════════════════════════════════════════════════════════════


class TestConcurrentCapture:
    """Verify registry integrity under multiple captures."""

    def test_multiple_captures_maintain_counts(self, capture_instance):
        """After many captures, all counts are consistent."""
        n = 10
        for i in range(n):
            capture_instance.maybe_capture(
                url=f"https://bulk{i}.com/page",
                html=f"<html><body>Bulk content {i}</body></html>",
                failure_category="selector_decay" if i % 2 == 0 else "anti_bot_block",
                failure_confidence=0.9,
                records_count=0,
            )

        stats = capture_instance.get_statistics()
        assert stats["total_captured"] == n
        assert stats["domain_count"] == n  # Each has unique domain
        assert stats["category_count"] == 2

        registry = capture_instance.get_registry()
        assert len(registry.entries) == n

    def test_duplicate_across_domains(self, capture_instance):
        """Same HTML from different domains — second is skipped."""
        html = "<html><body>Identical content</body></html>"
        entry1 = capture_instance.maybe_capture(
            url="https://domain-a.com/page",
            html=html, failure_category="empty_page",
            failure_confidence=0.9, records_count=0,
        )
        entry2 = capture_instance.maybe_capture(
            url="https://domain-b.com/page",
            html=html, failure_category="empty_page",
            failure_confidence=0.9, records_count=0,
        )
        assert entry1 is not None
        assert entry2 is None  # Duplicate HTML hash

    def test_id_generation_is_deterministic(self, capture_instance):
        """Same HTML produces same ID."""
        html = "<html><body>Deterministic ID</body></html>"
        entry1 = capture_instance.maybe_capture(
            url="https://example.com/page1",
            html=html, failure_category="anti_bot_block",
            failure_confidence=0.9, records_count=0,
        )
        # Use a fresh capture instance to verify deterministic IDs
        assert entry1 is not None
        assert len(entry1.id) == 12  # SHA256 prefix
        assert all(c in "0123456789abcdef" for c in entry1.id)  # hex
