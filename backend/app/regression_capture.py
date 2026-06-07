"""Regression Capture — Self-growing benchmark system.

Automatically captures extraction failures, archives failing HTML pages as
named fixtures, manages a registry of regressions, and can regenerate the
hostile benchmarks test suite with newly discovered edge cases.

This closes the evolutionary loop: every extraction failure enriches the
test suite, making future extraction more robust against that failure mode.

LAW: Every failure is a learning opportunity. The benchmark suite must grow
organically from real operational failures, not just synthetic scenarios.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class RegressionEntry:
    """A single captured regression case."""

    id: str = ""
    """Unique ID (SHA256 prefix of HTML content)."""

    url: str = ""
    """The URL that failed."""

    domain: str = ""
    """Extracted domain from the URL."""

    failure_category: str = ""
    """The FailureCategory value that was assigned."""

    failure_confidence: float = 0.0
    """Classifier confidence in this classification."""

    html_preview: str = ""
    """First 200 chars of the captured HTML for quick inspection."""

    html_size: int = 0
    """Size of captured HTML in bytes."""

    captured_at: float = 0.0
    """Unix timestamp of capture."""

    schema_fields: list[str] = field(default_factory=list)
    """The schema fields in use when failure occurred."""

    telemetry_snapshot: dict = field(default_factory=dict)
    """Snapshot of telemetry at time of failure."""

    fixture_filename: str = ""
    """Name of the fixture file in fixtures / pages/."""

    replay_test_generated: bool = False
    """Whether a replay test has been generated for this case."""


@dataclass
class RegressionRegistry:
    """Persistent registry of all captured regressions."""

    entries: list[RegressionEntry] = field(default_factory=list)
    total_captured: int = 0
    total_with_replay_tests: int = 0
    last_capture_at: float = 0.0
    domain_coverage: dict[str, int] = field(default_factory=dict)
    """How many regressions per domain."""

    category_coverage: dict[str, int] = field(default_factory=dict)
    """How many regressions per failure category."""


# ═══════════════════════════════════════════════════════════════════════
# Regression Capture Engine
# ═══════════════════════════════════════════════════════════════════════


class RegressionCapture:
    """Automatically captures extraction failures as benchmark fixtures.

    The capture criteria are:
      - Extraction returned zero records after a successful fetch
      - Extraction quality was below the configured threshold
      - A failure was classified with confidence >= min_confidence

    Each capture:
      1. Hashes the HTML content to produce a unique fixture ID
      2. Saves the HTML to fixtures / pages/{id}.html
      3. Registers metadata in the regression registry
      4. Optionally generates a pytest replay test

    The registry is persisted to backend / data / regression_registry.json.
    """

    def __init__(
        self,
        fixtures_dir: str | None = None,
        registry_path: str | None = None,
        min_confidence: float = 0.5,
        min_html_length: int = 100,
        auto_archive: bool = True,
    ) -> None:
        if fixtures_dir is None:
            fixtures_dir = str(Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pages")
        if registry_path is None:
            registry_path = str(Path(__file__).resolve().parent.parent / "data" / "regression_registry.json")
        self._fixtures_dir = Path(fixtures_dir)
        self._registry_path = Path(registry_path)
        self._min_confidence = min_confidence
        self._min_html_length = min_html_length
        self._auto_archive = auto_archive

        # Ensure directories exist
        self._fixtures_dir.mkdir(parents=True, exist_ok=True)
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)

        self._registry = self._load_registry()

    # ── Public API ─────────────────────────────────────────────────────

    def maybe_capture(
        self,
        url: str,
        html: str | None,
        failure_category: str = "",
        failure_confidence: float = 0.0,
        records_count: int = 0,
        schema_fields: list[str] | None = None,
        telemetry: dict | None = None,
        force: bool = False,
    ) -> RegressionEntry | None:
        """Evaluate and potentially capture a regression case.

        Args:
            url: The URL that was extracted.
            html: Raw HTML from the page (None if fetch failed).
            failure_category: Classified failure category string.
            failure_confidence: Confidence in the classification [0, 1].
            records_count: Number of records extracted (0 = failure).
            schema_fields: Schema field names in use.
            telemetry: Telemetry snapshot dict.
            force: If True, capture even if criteria aren't met.

        Returns:
            A RegressionEntry if captured, None otherwise.

        """
        # Determine if capture is warranted
        if not force:
            if records_count > 0 and failure_confidence < self._min_confidence:
                return None
            if not html or len(html.strip()) < self._min_html_length:
                return None

        # Generate unique ID from HTML content hash
        content_to_hash = html or url
        content_id = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()[:12]

        # Check for duplicate
        if self._is_duplicate(content_id):
            logger.debug("Regression %s already captured, skipping", content_id)
            return None

        domain = self._extract_domain(url)
        fixture_name = f"{content_id}.html"

        # Archive the HTML
        if self._auto_archive and html:
            self._save_fixture(fixture_name, html)

        # Build entry
        entry = RegressionEntry(
            id=content_id,
            url=url,
            domain=domain,
            failure_category=failure_category or "unknown",
            failure_confidence=round(failure_confidence, 3),
            html_preview=(html or "")[:200],
            html_size=len(html or ""),
            captured_at=time.time(),
            schema_fields=schema_fields or [],
            telemetry_snapshot=telemetry or {},
            fixture_filename=fixture_name,
        )

        # Register
        self._registry.entries.append(entry)
        self._registry.total_captured += 1
        self._registry.last_capture_at = time.time()
        self._registry.domain_coverage[domain] = self._registry.domain_coverage.get(domain, 0) + 1
        cat = failure_category or "unknown"
        self._registry.category_coverage[cat] = self._registry.category_coverage.get(cat, 0) + 1

        self._save_registry()

        logger.info(
            "Regression captured: %s | domain=%s category=%s confidence=%.2f size=%d",
            content_id,
            domain,
            failure_category,
            failure_confidence,
            entry.html_size,
        )

        return entry

    def generate_replay_test(self, entry_id: str) -> str | None:
        """Generate a pytest replay test for a captured regression.

        Args:
            entry_id: The regression entry ID.

        Returns:
            Generated test code as a string, or None if entry not found.

        """
        entry = self._get_entry(entry_id)
        if not entry:
            return None

        # Check if fixture file exists
        fixture_path = self._fixtures_dir / entry.fixture_filename
        if not fixture_path.exists():
            logger.warning("Fixture file %s not found, cannot generate test", fixture_path)
            return None

        test_code = self._build_replay_test(entry)
        entry.replay_test_generated = True
        self._registry.total_with_replay_tests = sum(1 for e in self._registry.entries if e.replay_test_generated)
        self._save_registry()

        return test_code

    def generate_all_replay_tests(self) -> str:
        """Generate replay tests for all captured regressions that don't have one yet.

        Returns:
            Concatenated test code as a single string.

        """
        all_tests = []
        for entry in self._registry.entries:
            if not entry.replay_test_generated:
                test_code = self._build_replay_test(entry)
                if test_code:
                    entry.replay_test_generated = True
                    all_tests.append(test_code)

        self._registry.total_with_replay_tests = sum(1 for e in self._registry.entries if e.replay_test_generated)
        self._save_registry()

        return "\n\n# ===== TEST SEPARATOR =====\n\n".join(all_tests)

    def classify_severity(self, entry: RegressionEntry) -> str:
        """Classify the severity of a regression entry.

        Severity levels:
          - critical: Anti-bot block, captcha, IP ban — the site is actively hostile
          - high: Selector decay, hydration failure, empty page — extraction failed structurally
          - medium: Low quality, partial extraction, selector mismatch — got something but not enough
          - low: Connection timeout, HTTP error, rate limited — transient, likely temporary
          - info: All other categories — captured for awareness
        """
        high_severity_categories = {
            "anti_bot_block",
            "captcha",
            "ip_banned",
            "browser_crash",
        }
        med_severity_categories = {
            "selector_decay",
            "hydration_failure",
            "lazy_load_timeout",
            "empty_page",
            "no_records_extracted",
            "malformed_dom",
        }
        low_severity_categories = {
            "low_quality_extraction",
            "partial_extraction",
            "selector_mismatch",
            "connection_timeout",
            "http_error",
            "rate_limited",
            "dns_resolution_failure",
        }

        cat = entry.failure_category or "unknown"
        if cat in high_severity_categories:
            return "critical"
        if cat in med_severity_categories:
            return "high"
        if cat in low_severity_categories:
            return "low"
        return "info"

    def prune_fixtures(self, max_age_days: int = 30, max_fixtures: int = 200) -> int:
        """Prune old fixture files to manage disk usage.

        Args:
            max_age_days: Remove fixtures older than this (default 30)
            max_fixtures: Maximum number of fixtures to keep (default 200)

        Returns:
            Number of fixtures pruned

        """
        if not self._fixtures_dir.exists():
            return 0

        cut_off = time.time() - (max_age_days * 86400)

        # Get all fixture files with their modification times
        fixtures = []
        for f in self._fixtures_dir.iterdir():
            if f.suffix == ".html":
                fixtures.append((f.stat().st_mtime, f))

        # Sort by modification time (oldest first)
        fixtures.sort(key=lambda x: x[0])

        to_remove = []

        # Remove fixtures older than max_age_days
        for mtime, fpath in fixtures:
            if mtime < cut_off:
                to_remove.append(fpath)

        # If still over limit, remove oldest
        remaining = len(fixtures) - len(to_remove)
        if remaining > max_fixtures:
            keep_set = {f for _, f in fixtures[-max_fixtures:]}
            extra_fixtures = [f for _, f in fixtures if f not in keep_set and f not in to_remove]
            to_remove.extend(extra_fixtures)

        # Also clean up registry entries for removed fixtures
        removed_names = {f.name for f in to_remove}
        self._registry.entries = [e for e in self._registry.entries if e.fixture_filename not in removed_names]

        # Actually delete files
        pruned = 0
        for fpath in to_remove:
            try:
                fpath.unlink()
                pruned += 1
            except OSError:
                pass  # nosec B110

        if pruned > 0:
            self._save_registry()
            logger.info("Pruned %d stale fixture files", pruned)

        return pruned

    def get_statistics(self) -> dict:
        """Return summary statistics of the regression archive."""
        # Compute severity distribution
        severity_dist = {"critical": 0, "high": 0, "low": 0, "info": 0}
        for entry in self._registry.entries:
            sev = self.classify_severity(entry)
            severity_dist[sev] = severity_dist.get(sev, 0) + 1

        return {
            "total_captured": self._registry.total_captured,
            "total_with_replay_tests": self._registry.total_with_replay_tests,
            "last_capture_at": self._registry.last_capture_at,
            "domain_count": len(self._registry.domain_coverage),
            "category_count": len(self._registry.category_coverage),
            "severity_distribution": severity_dist,
            "domain_coverage": dict(
                sorted(
                    self._registry.domain_coverage.items(),
                    key=lambda x: -x[1],
                )[:20],
            ),
            "category_coverage": dict(
                sorted(
                    self._registry.category_coverage.items(),
                    key=lambda x: -x[1],
                ),
            ),
            "recent_captures": [
                {
                    "id": e.id,
                    "domain": e.domain,
                    "category": e.failure_category,
                    "severity": self.classify_severity(e),
                    "confidence": e.failure_confidence,
                    "captured_at": e.captured_at,
                    "fixture": e.fixture_filename,
                    "has_replay_test": e.replay_test_generated,
                }
                for e in sorted(
                    self._registry.entries,
                    key=lambda x: x.captured_at,
                    reverse=True,
                )[:20]
            ],
        }

    def get_registry(self) -> RegressionRegistry:
        """Return the full registry."""
        return self._registry

    # ── Internal ───────────────────────────────────────────────────────

    def _is_duplicate(self, content_id: str) -> bool:
        """Check if a content hash already exists in the registry."""
        return any(e.id == content_id for e in self._registry.entries)

    def _save_fixture(self, filename: str, html: str) -> None:
        """Save HTML content as a fixture file."""
        fixture_path = self._fixtures_dir / filename
        fixture_path.write_text(html, encoding="utf-8")
        logger.debug("Saved fixture: %s (%d bytes)", fixture_path, len(html))

    def _load_registry(self) -> RegressionRegistry:
        """Load the registry from disk, or return an empty one."""
        if not self._registry_path.exists():
            return RegressionRegistry()

        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            entries = [RegressionEntry(**e) for e in data.get("entries", [])]
            # Rebuild computed counts for backwards compatibility
            total_with_tests = sum(1 for e in entries if e.replay_test_generated)
            domain_cov: dict[str, int] = {}
            category_cov: dict[str, int] = {}
            for e in entries:
                domain_cov[e.domain] = domain_cov.get(e.domain, 0) + 1
                cat = e.failure_category or "unknown"
                category_cov[cat] = category_cov.get(cat, 0) + 1

            return RegressionRegistry(
                entries=entries,
                total_captured=data.get("total_captured", len(entries)),
                total_with_replay_tests=data.get("total_with_replay_tests", total_with_tests),
                last_capture_at=data.get("last_capture_at", 0.0),
                domain_coverage=domain_cov,
                category_coverage=category_cov,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load regression registry: %s", e)
            return RegressionRegistry()

    def _save_registry(self) -> None:
        """Persist the registry to disk.

        The write is performed atomically by writing to a sibling
        ``.tmp`` file and then renaming it on top of the target. A
        plain ``write_text`` would leave a half-written file if the
        process were killed mid-write, losing all captured regressions
        and silently breaking the next startup. The rename is atomic
        on POSIX (and on Windows when the target exists), so a reader
        either sees the previous valid file or the new one.
        """
        data = {
            "entries": [asdict(e) for e in self._registry.entries],
            "total_captured": self._registry.total_captured,
            "total_with_replay_tests": self._registry.total_with_replay_tests,
            "last_capture_at": self._registry.last_capture_at,
        }
        payload = json.dumps(data, indent=2, default=str)
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._registry_path.with_suffix(self._registry_path.suffix + ".tmp")
        # Write to the tmp file first, then replace. ``os.replace`` is
        # atomic on POSIX and on Windows when the target exists, so the
        # rename either happens in full or not at all.
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Some filesystems (e.g. tmpfs) do not support fsync;
                # the rename is still atomic, so this is best-effort.
                pass
        os.replace(tmp_path, self._registry_path)

    def _get_entry(self, entry_id: str) -> RegressionEntry | None:
        """Look up an entry by ID."""
        for e in self._registry.entries:
            if e.id == entry_id:
                return e
        return None

    def _build_replay_test(self, entry: RegressionEntry) -> str | None:
        """Build a pytest test function for replaying this regression."""
        fixture_path = self._fixtures_dir / entry.fixture_filename
        if not fixture_path.exists():
            return None

        safe_name = f"test_replay_{entry.id}"
        category = entry.failure_category or "unknown"

        schema_args = ", ".join(repr(f) for f in entry.schema_fields[:5]) if entry.schema_fields else '"company_name"'

        test_code = f"""
def {safe_name}(hostile_base_url):
    \"\"\"Replay regression: {category} on {entry.domain} (confidence={entry.failure_confidence}).\"\"\"
    import asyncio
    from app.models import SchemaField, FieldType
    from app.scraper import scrape_url

    fields = [
        SchemaField(name={schema_args}, field_type=FieldType.STRING, required=True),
    ]
    url = f"{{hostile_base_url}}/regression/{entry.id}"
    results = asyncio.run(scrape_url(url, fields, min_record_score=0.2))
    # Expected: extraction should handle this failure mode gracefully
    assert len(results) == 0, f"Expected 0 results for regression fixture {entry.id}, got {{len(results)}}"
"""

        return test_code.strip()

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from a URL."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or "unknown"
        except Exception:
            return "unknown"


# Module-level singleton
_capture: RegressionCapture | None = None
_capture_lock = threading.Lock()


def get_regression_capture() -> RegressionCapture:
    """Return the singleton RegressionCapture instance.

    The double-checked locking pattern (module-level ``_capture_lock``
    + a fast-path identity check) is used to avoid the time-of-check
    to time-of-use (TOCTOU) race where two threads simultaneously
    observe ``_capture is None`` and each construct a fresh
    ``RegressionCapture``. Without the lock, the second writer would
    clobber the first writer's state, dropping every regression
    captured between the two ``RegressionCapture()`` calls.
    """
    global _capture
    if _capture is None:
        with _capture_lock:
            if _capture is None:
                _capture = RegressionCapture()
    return _capture
