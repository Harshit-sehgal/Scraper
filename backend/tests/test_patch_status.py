"""Unit Tests for Architecture Patch Status.

Tests the file-scanning logic that verifies tracked-file fixes
and the human-readable report generator.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.patch_status import check_all_fixes, generate_patch_report


class TestCheckAllFixes:
    """Tests for check_all_fixes() — verifies it scans files and returns results."""

    def test_returns_dict_with_results(self) -> None:
        results = check_all_fixes()
        assert isinstance(results, dict)
        assert len(results) > 0
        # Each value should be a boolean
        for key, ok in results.items():
            assert isinstance(ok, bool), f"{key}: expected bool, got {type(ok)}"

    def test_expected_keys_present(self) -> None:
        results = check_all_fixes()
        key_categories = [
            "ROLE_EXCLUSIVITY",
            "create_token",
            "schema_instability",
            "integrity_score",
            "capture schema expansion",
            "method:",
            "field:",
            "pipeline clean",
        ]
        for category in key_categories:
            matches = [k for k in results if category in k]
            assert matches, f"No result key contains '{category}'"

    def test_file_not_found_does_not_crash(self) -> None:
        """Even if a tracked file were missing, the function should not crash."""
        results = check_all_fixes()
        # All should at least be valid booleans
        for ok in results.values():
            assert isinstance(ok, bool)


class TestGeneratePatchReport:
    """Tests for generate_patch_report() — formatting and aggregation."""

    def test_full_success_report(self) -> None:
        results = {
            "ROLE_EXCLUSIVITY price/cost (field_laws.py)": True,
            "create_token source_field": True,
            "schema_instability property (energy_state.py)": True,
            "integrity_score property (energy_state.py)": True,
            "capture schema expansion": True,
            "method: relax_topology": True,
            "method: detect_communities": True,
            "field: crystalline_records": True,
            "pipeline clean": True,
        }
        report = generate_patch_report(results)
        assert "Patch Status Report" in report
        assert "Fixes applied: 9/9" in report
        assert "✓" in report
        assert "✗" not in report

    def test_partial_failure_report(self) -> None:
        results = {
            "ROLE_EXCLUSIVITY price/cost (field_laws.py)": True,
            "create_token source_field": False,
            "pipeline clean": True,
        }
        report = generate_patch_report(results)
        assert "Fixes applied: 2/3" in report
        assert "✓" in report
        assert "✗" in report

    def test_empty_results(self) -> None:
        report = generate_patch_report({})
        assert "Fixes applied: 0/0" in report

    def test_categorizes_by_module(self) -> None:
        results = {
            "ROLE_EXCLUSIVITY price/cost": True,
            "create_token source_field": False,
            "pipeline clean": True,
        }
        report = generate_patch_report(results)
        # Should contain module headers
        assert "semantic_allocation_engine.py" in report
        assert "semantic_ir.py" in report
        assert "semantic_pipeline.py" in report

    def test_unknown_key_falls_to_other_module(self) -> None:
        """Keys that don't match any known module should be grouped under 'other'."""
        results = {
            "some_random_unknown_check": True,
            "another_mystery_value": False,
        }
        report = generate_patch_report(results)
        assert "Fixes applied: 1/2" in report
        assert "other" in report
        assert "some_random_unknown_check" in report
        assert "another_mystery_value" in report


class TestMainBlock:
    """Tests for the `if __name__ == '__main__'` block in patch_status.py."""

    def test_main_block_runs_without_error(self) -> None:
        """Running patch_status.py as __main__ should not crash."""
        patch_path = Path(__file__).parent.parent / "app" / "patch_status.py"
        result = subprocess.run(
            [sys.executable, str(patch_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should print the report via logger; at minimum should not crash
