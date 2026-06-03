"""
Tests for the research-shell quarantine in app/url_redirects.py.

`url_redirects.py` historically imported `app.acquisition_state` at
module top level, which forced the research shell into the product
kernel's startup import graph. This file pins the new contract:

1. Importing `app.url_redirects` does NOT load `app.acquisition_state`.
2. Calling `build_redirect_info()` triggers the lazy import.
3. The public behavior of `build_redirect_info` is unchanged.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def clean_url_redirects_import():
    """Ensure app.url_redirects and app.acquisition_state are not cached.

    This forces a fresh import of url_redirects so we can verify the
    lazy-import contract.
    """
    for name in (
        "app.url_redirects",
        "app.acquisition_state",
    ):
        sys.modules.pop(name, None)
    yield
    # Clean up after the test so subsequent tests start fresh.
    for name in (
        "app.url_redirects",
        "app.acquisition_state",
    ):
        sys.modules.pop(name, None)


def test_url_redirects_does_not_load_acquisition_state_at_import(clean_url_redirects_import) -> None:
    """Importing app.url_redirects must NOT pull in app.acquisition_state.

    This is the contract that the Phase R2 quarantine established.
    """
    importlib.import_module("app.url_redirects")

    assert "app.acquisition_state" not in sys.modules, (
        "app.url_redirects eagerly imported app.acquisition_state at "
        "module load time. The lazy import in build_redirect_info() is "
        "broken."
    )


def test_build_redirect_info_triggers_lazy_import(clean_url_redirects_import) -> None:
    """Calling build_redirect_info must trigger the lazy import."""
    import app.url_redirects

    assert "app.acquisition_state" not in sys.modules

    app.url_redirects.build_redirect_info(
        original_url="https://example.com/a/b/c",
        final_url="https://example.com/",
    )

    assert "app.acquisition_state" in sys.modules, (
        "build_redirect_info() did not trigger the lazy import of "
        "app.acquisition_state. The lineage construction will fail at "
        "runtime if this contract is violated."
    )


def test_build_redirect_info_returns_expected_dict(clean_url_redirects_import) -> None:
    """The public behavior of build_redirect_info is unchanged."""
    import app.url_redirects

    result = app.url_redirects.build_redirect_info(
        original_url="https://example.com/a/b/c",
        final_url="https://example.com/",
    )
    # The AcquisitionLineage dict contains a few stable keys we can
    # assert on. We do not assert the full dict (the research shell
    # controls its shape) — just that the call succeeds and the
    # documented fields are present.
    assert result["original_url"] == "https://example.com/a/b/c"
    assert result["final_url"] == "https://example.com/"
    assert result["redirected"] is True
    # The classification comes from _detect_redirect, which is in the
    # kernel and was not changed by this refactor.
    assert result["redirect_type"] in {"session_expired", "homepage_redirect", "path_changed"}


def test_detect_redirect_works_without_acquisition_state(clean_url_redirects_import) -> None:
    """_detect_redirect is pure-Python and must not require research imports."""
    import app.url_redirects

    # Should work without triggering the acquisition_state import.
    result = app.url_redirects._detect_redirect(
        "https://example.com/a",
        "https://example.com/a",
    )
    assert result["redirected"] is False
    assert result["redirect_type"] == "none"
    assert "app.acquisition_state" not in sys.modules
