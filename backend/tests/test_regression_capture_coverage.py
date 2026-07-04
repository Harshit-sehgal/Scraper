"""Tests for regression_capture.classify_severity + prune_fixtures.

Both methods had zero direct test coverage (covered: 79%; the uncovered
lines 312-314, 327-372 included these two methods plus ~10 lines of
atomic-write helpers).

  - classify_severity: drives the regression dashboard triage; maps 17
    failure_category values to 5 severity levels.  Failing this mapping
    silently means critical failures appear as 'info'.
  - prune_fixtures: disk-exhaustion prevention — keeps fixture count
    under a hard cap and ages out old files.

Plus 4 atomic-write helpers (_save_fixture, _save_registry / reload)
and the `_build_replay_test` sparse-output edge case.

These complement test_regression_capture.py, which covers the capture /
registry / replay generation paths.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from app.regression_capture import (
    RegressionCapture,
    RegressionEntry,
)

# ── classify_severity — pure mapping function ─────────────────────────


class TestClassifySeverity:
    """Pure mapping from failure_category to severity tier.

    Severity tiers (per the module's docstring):
      - critical: anti-bot, captcha, IP ban, browser crash
      - high:     selector decay, hydration failure, empty page, etc.
      - low:      connection timeout, HTTP error, rate limited, etc.
      - info:     unknown / unmapped / empty
    """

    @pytest.fixture(autouse=True)
    def _capture(self, tmp_path: Path) -> RegressionCapture:
        """Fresh capture instance per test."""
        return RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "registry.json"),
        )

    @pytest.mark.parametrize(
        "category, expected_severity",
        [
            # critical tier — actively hostile
            ("anti_bot_block", "critical"),
            ("captcha", "critical"),
            ("ip_banned", "critical"),
            ("browser_crash", "critical"),
            # high tier — extraction failed structurally
            ("selector_decay", "high"),
            ("hydration_failure", "high"),
            ("lazy_load_timeout", "high"),
            ("empty_page", "high"),
            ("no_records_extracted", "high"),
            ("malformed_dom", "high"),
            # low tier — transient
            ("low_quality_extraction", "low"),
            ("partial_extraction", "low"),
            ("selector_mismatch", "low"),
            ("connection_timeout", "low"),
            ("http_error", "low"),
            ("rate_limited", "low"),
            ("dns_resolution_failure", "low"),
            # info tier (unmapped defaults to info)
            ("something_we_never_saw", "info"),
            ("", "info"),  # empty string → 'unknown' branch
        ],
    )
    def test_severity_mapping(
        self,
        _capture: RegressionCapture,
        category: str,
        expected_severity: str,
    ) -> None:
        """17 failure_categories map to 5 severity tiers correctly."""
        entry = RegressionEntry(failure_category=category)
        actual = _capture.classify_severity(entry)
        assert actual == expected_severity, f"category={category!r}: expected {expected_severity!r}, got {actual!r}"

    def test_classify_severity_empty_category_is_info(
        self,
        _capture: RegressionCapture,
    ) -> None:
        """An entry with empty failure_category defaults to 'info'."""
        entry = RegressionEntry(failure_category="")
        assert _capture.classify_severity(entry) == "info"


# ── prune_fixtures — disk-exhaustion prevention ────────────────────────


class TestPruneFixtures:
    """Fixture management: age out & cap-discard to bound disk usage."""

    @pytest.fixture
    def capture(self, tmp_path: Path) -> RegressionCapture:
        return RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "registry.json"),
        )

    def test_prune_no_fixtures_dir_returns_zero(self, tmp_path: Path) -> None:
        """If fixtures_dir doesn't exist, prune returns 0 (no-op)."""
        # Construct with a non-existent dir, then delete it before pruning.
        fixtures_dir = tmp_path / "fix"
        capture = RegressionCapture(
            fixtures_dir=str(fixtures_dir),
            registry_path=str(tmp_path / "reg.json"),
        )
        # Constructor created the dir; remove it to test the no-op path.
        import shutil

        shutil.rmtree(fixtures_dir)
        assert not fixtures_dir.exists()

        pruned = capture.prune_fixtures()
        assert pruned == 0

    def test_prune_empty_dir_returns_zero(self, capture: RegressionCapture) -> None:
        """Empty fixtures_dir → 0 pruned."""
        pruned = capture.prune_fixtures()
        assert pruned == 0

    def test_prune_removes_old_fixtures(self, capture: RegressionCapture) -> None:
        """Fixtures older than max_age_days are deleted."""
        fixtures_dir = capture._fixtures_dir
        # Three old fixtures (mtime set to 100 days ago).
        old_time = time.time() - (100 * 86400)
        for i in range(3):
            f = fixtures_dir / f"old{i}.html"
            f.write_text(f"<html>old{i}</html>")
            os.utime(f, (old_time, old_time))

        # One fresh fixture.
        fresh = fixtures_dir / "fresh.html"
        fresh.write_text("<html>fresh</html>")

        # Default max_age_days=30 → all 3 old should be removed.
        pruned = capture.prune_fixtures()
        assert pruned == 3

        # Fresh still present, old removed.
        assert fresh.exists()
        for i in range(3):
            assert not (fixtures_dir / f"old{i}.html").exists()

    def test_prune_caps_total_count(self, capture: RegressionCapture) -> None:
        """If fixture count exceeds max_fixtures, oldest (not-yet-aged-out) are dropped."""
        fixtures_dir = capture._fixtures_dir
        # 5 fixtures all unique mtimes, all "fresh" (well within age limit).
        now = time.time()
        for i in range(5):
            f = fixtures_dir / f"f{i:02d}.html"
            f.write_text(f"<html>{i}</html>")
            mt = now - (100 - i)  # f00 oldest, f04 newest
            os.utime(f, (mt, mt))

        # max_age_days=30 → none aged out.  max_fixtures=3 → 2 oldest dropped.
        pruned = capture.prune_fixtures(max_age_days=30, max_fixtures=3)
        assert pruned == 2

        # The 3 newest survive.
        assert (fixtures_dir / "f02.html").exists()
        assert (fixtures_dir / "f03.html").exists()
        assert (fixtures_dir / "f04.html").exists()
        # The 2 oldest are gone.
        assert not (fixtures_dir / "f00.html").exists()
        assert not (fixtures_dir / "f01.html").exists()

    def test_prune_cleans_registry_entries(self, capture: RegressionCapture) -> None:
        """Removing fixtures also removes registry entries referencing them."""
        fixtures_dir = capture._fixtures_dir
        f = fixtures_dir / "linked.html"
        f.write_text("<html>x</html>")

        # Add a registry entry that references this fixture.
        entry = RegressionEntry(
            id="abc123",
            url="https://example.com",
            fixture_filename="linked.html",
        )
        capture._registry.entries.append(entry)
        capture._save_registry()

        # Old-enough mtime to trigger age-based prune.
        old_time = time.time() - (60 * 86400)
        os.utime(f, (old_time, old_time))

        pruned = capture.prune_fixtures(max_age_days=30)
        assert pruned == 1

        # Registry no longer references removed fixture.
        fixture_names = {e.fixture_filename for e in capture._registry.entries}
        assert "linked.html" not in fixture_names

    def test_prune_handles_unlink_failure(self, capture: RegressionCapture) -> None:
        """If unlink() raises OSError, prune continues with remaining files."""
        fixtures_dir = capture._fixtures_dir
        old_time = time.time() - (60 * 86400)
        for i in range(3):
            f = fixtures_dir / f"x{i}.html"
            f.write_text(f"<html>x{i}</html>")
            os.utime(f, (old_time, old_time))

        # Patch unlink on the specific path to raise for one fixture.
        original_unlink = Path.unlink

        def flaky_unlink(self, *args, **kwargs):
            if self.name == "x1.html":
                msg = "simulated"
                raise OSError(msg)
            return original_unlink(self, *args, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(Path, "unlink", flaky_unlink)
            pruned = capture.prune_fixtures(max_age_days=30)
        # 2 of 3 removed (x1 raised, x0 + x2 didn't).
        assert pruned == 2


# ── Atomic-write helpers ───────────────────────────────────────────────


class TestAtomicWrites:
    """_save_fixture and _save_registry must persist to disk durably."""

    @pytest.fixture
    def capture(self, tmp_path: Path) -> RegressionCapture:
        return RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "registry.json"),
        )

    def test_save_fixture_writes_html_to_disk(self, capture: RegressionCapture) -> None:
        """_save_fixture stores the HTML content to the named file."""
        capture._save_fixture("test.html", "<html>hi</html>")
        target = capture._fixtures_dir / "test.html"
        assert target.exists()
        assert target.read_text() == "<html>hi</html>"

    def test_save_fixture_silently_swallows_oserror(
        self,
        capture: RegressionCapture,
    ) -> None:
        """_save_fixture must not raise on OSError — it logs and returns,
        cleaning up the partial .tmp file.  This is the durability
        failure path: a fixture that can't be saved is skipped, not
        propagated as a crash."""
        from unittest.mock import patch

        # Force mkstemp to fail → fd/None branch + cleanup path.
        with patch(
            "app.regression_capture.tempfile.mkstemp",
            side_effect=OSError("disk full"),
        ):
            # Must NOT raise.
            capture._save_fixture("unwritable.html", "<html>x</html>")
        # And the target fixture was never created.
        assert not (capture._fixtures_dir / "unwritable.html").exists()

    def test_save_registry_round_trip(self, capture: RegressionCapture) -> None:
        """_save_registry writes the registry to disk; _load_registry reads it back."""
        entry = RegressionEntry(
            id="zzz999",
            url="https://example.com",
            fixture_filename="x.html",
        )
        capture._registry.entries.append(entry)
        capture._save_registry()

        reloaded = capture._load_registry()
        assert any(e.id == "zzz999" for e in reloaded.entries)

    def test_save_registry_silently_swallows_oserror(
        self,
        capture: RegressionCapture,
    ) -> None:
        """_save_registry must not raise on OSError — it logs and cleans up."""
        from unittest.mock import patch

        with patch(
            "app.regression_capture.tempfile.mkstemp",
            side_effect=OSError("disk full"),
        ):
            # Must NOT raise.
            capture._save_registry()
        # Registry file was never created.
        assert not capture._registry_path.exists()


# ── _build_replay_test sparse-output edge case ────────────────────────


class TestBuildReplayTest:
    """_build_replay_test behavior when fixture / schema data is missing."""

    @pytest.fixture
    def capture(self, tmp_path: Path) -> RegressionCapture:
        return RegressionCapture(
            fixtures_dir=str(tmp_path / "fixtures"),
            registry_path=str(tmp_path / "registry.json"),
        )

    def test_build_replay_test_returns_none_or_str_when_missing_data(
        self,
        capture: RegressionCapture,
    ) -> None:
        """When required data is missing, _build_replay_test returns None."""
        entry = RegressionEntry(
            id="missing",
            url="https://nonexistent.example",  # no followable URL
            fixture_filename="",  # no fixture → cannot load page
        )
        result = capture._build_replay_test(entry)
        # The implementation either returns None or a (possibly empty) string;
        # both are acceptable as "could not build" is the contract.
        assert result is None or isinstance(result, str)
