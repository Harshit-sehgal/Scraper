"""Regression tests for the file audit ledger generator."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "artifacts" / "audit" / "gen_full_ledger.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_full_ledger", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_file_ledger_generator_does_not_hardcode_stale_validation_failures() -> None:
    generator = _load_generator()

    assert generator.KNOWN_FILE_ISSUES == {}


def test_file_ledger_generator_classifies_root_eslint_config() -> None:
    generator = _load_generator()

    classification, purpose, skip_reason, owned, confidence = generator.classify("eslint.config.js")

    assert classification == "config"
    assert purpose == "project/tooling configuration"
    assert skip_reason == ""
    assert owned is True
    assert confidence == "high"
