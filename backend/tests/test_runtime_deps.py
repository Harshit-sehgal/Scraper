"""Tests for app.runtime_deps — DI swapping, dependency import checks."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestSetDeps:
    """set_deps() swaps the module-level callables."""

    def test_set_deps_swaps_schedule(self) -> None:
        from app.runtime_deps import set_deps

        def fake_schedule(coro):
            pass

        set_deps(schedule=fake_schedule)
        import app.runtime_deps as rd

        assert rd.schedule_task_fn is fake_schedule
        # Restore
        set_deps(schedule=None)

    def test_set_deps_swaps_run_job(self) -> None:
        from app.runtime_deps import set_deps

        async def fake_run_job(job_id: str) -> None:
            pass

        set_deps(run_job=fake_run_job)
        import app.runtime_deps as rd

        assert rd.run_job_coro_fn is fake_run_job
        set_deps(run_job=None)

    def test_set_deps_none_restores_default(self) -> None:
        from app.runtime_deps import _default_run_job, set_deps

        set_deps(run_job=None)
        import app.runtime_deps as rd

        assert rd.run_job_coro_fn is _default_run_job


class TestCheckRuntimeDeps:
    """check_runtime_deps() validates required and optional packages."""

    def test_all_required_present(self) -> None:
        """If all required packages are importable, no error is raised."""
        from app.runtime_deps import check_runtime_deps

        result = check_runtime_deps(fail_on_missing=True)
        assert result["missing_required"] == []

    def test_missing_required_raises(self) -> None:
        """If a required package is missing, RuntimeError is raised."""
        from app.runtime_deps import check_runtime_deps

        with patch("app.runtime_deps.REQUIRED_PACKAGES", [("nonexistent_pkg_xyz", "nonexistent-pkg")]):
            with pytest.raises(RuntimeError, match="Missing required packages"):
                check_runtime_deps(fail_on_missing=True)

    def test_missing_required_soft_check(self) -> None:
        """With fail_on_missing=False, missing required packages are returned but no error raised."""
        from app.runtime_deps import check_runtime_deps

        with patch("app.runtime_deps.REQUIRED_PACKAGES", [("nonexistent_pkg_xyz", "nonexistent-pkg")]):
            result = check_runtime_deps(fail_on_missing=False)
            assert "nonexistent-pkg" in result["missing_required"]

    def test_missing_optional_returns_list(self) -> None:
        """Missing optional packages are listed but don't raise."""
        from app.runtime_deps import check_runtime_deps

        with patch("app.runtime_deps.OPTIONAL_PACKAGES", [("nonexistent_opt_xyz", "nonexistent-opt")]):
            result = check_runtime_deps(fail_on_missing=True)
            assert "nonexistent-opt" in result["missing_optional"]

    def test_returns_expected_keys(self) -> None:
        from app.runtime_deps import check_runtime_deps

        result = check_runtime_deps(fail_on_missing=False)
        assert "missing_required" in result
        assert "missing_optional" in result
        assert isinstance(result["missing_required"], list)
        assert isinstance(result["missing_optional"], list)


class TestPackageLists:
    """REQUIRED_PACKAGES and OPTIONAL_PACKAGES have sensible contents."""

    def test_required_packages_not_empty(self) -> None:
        from app.runtime_deps import REQUIRED_PACKAGES

        assert len(REQUIRED_PACKAGES) > 0

    def test_optional_packages_not_empty(self) -> None:
        from app.runtime_deps import OPTIONAL_PACKAGES

        assert len(OPTIONAL_PACKAGES) > 0

    def test_required_packages_are_tuples(self) -> None:
        from app.runtime_deps import REQUIRED_PACKAGES

        for module_name, pip_name in REQUIRED_PACKAGES:
            assert isinstance(module_name, str)
            assert isinstance(pip_name, str)
            assert len(module_name) > 0
            assert len(pip_name) > 0

    def test_optional_packages_are_tuples(self) -> None:
        from app.runtime_deps import OPTIONAL_PACKAGES

        for module_name, pip_name in OPTIONAL_PACKAGES:
            assert isinstance(module_name, str)
            assert isinstance(pip_name, str)

    def test_core_deps_in_required(self) -> None:
        from app.runtime_deps import REQUIRED_PACKAGES

        modules = {m for m, _ in REQUIRED_PACKAGES}
        assert "pydantic" in modules
        assert "fastapi" in modules
        assert "httpx" in modules

    def test_playwright_in_optional(self) -> None:
        from app.runtime_deps import OPTIONAL_PACKAGES

        modules = {m for m, _ in OPTIONAL_PACKAGES}
        assert "playwright" in modules

    def test_aiosqlite_in_optional(self) -> None:
        from app.runtime_deps import OPTIONAL_PACKAGES

        modules = {m for m, _ in OPTIONAL_PACKAGES}
        assert "aiosqlite" in modules
