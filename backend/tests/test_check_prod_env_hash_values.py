"""Static + behavioral guard for F-SCRIPT-002 / scripts/check_prod_env.py.

Pre-fix, ``scripts/check_prod_env.py:82-110`` used a custom dotenv
parser that stripped trailing ``#`` comments via
``value.partition("#")[0].strip()``. Any value containing a literal
``#`` (e.g. ``GRAFANA_PASSWORD=Nz4HdRU#not-a-real-password``) had its
hash+anything-after silently truncated to ``Nz4HdRU`` — bypassing any
checks downstream that look at the *full* value.

The fix replaces the dot-splitting with a per-line parser that:

  - treats ``# this is a comment`` as a comment (leading ``#``);
  - honours ``KEY=value#with#hashes`` as a single raw value (the
    tail is part of the value, not a comment);
  - strips a single layer of matching surrounding ``"..."`` or
    ``'...'``.

We deliberately keep parsing local rather than reusing
``python-dotenv``: dotenv refuses files with unbalanced quotes (e.g.
when a JSON-array value embeds inner ``"``), while the historical
contract is tolerant of those as long as the wrapper quotes line up.

This test locks in four invariants:

1. ``load_env_file`` round-trips a simple ``KEY=value`` line.
2. ``load_env_file`` does NOT strip a literal ``#`` from the value.
3. Quoted values still have their wrapping quotes stripped (parity
   with the prior behaviour so other tests / loaders don't regress).
4. Lines that start with ``#`` are still treated as comments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_prod_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_prod_env_mod", SCRIPT)
    assert spec and spec.loader, f"could not import {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestCheckProdEnvParser:
    """``check_prod_env.py`` parses values verbatim — no hash-truncation."""

    def test_simple_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("PLAIN_KEY=plain_value\n", encoding="utf-8")
        mod = _load_module()
        parsed = mod.load_env_file(env_file)
        assert parsed["PLAIN_KEY"] == "plain_value", "F-SCRIPT-002: parser regressed; plain KEY=value is no longer round-tripped."

    def test_value_with_literal_hash_not_truncated(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        # The exact payload from the audit: a value containing ``#``.
        env_file.write_text(
            "GRAFANA_PASSWORD=Nz4HdRU#not-a-real-password\n",
            encoding="utf-8",
        )
        mod = _load_module()
        parsed = mod.load_env_file(env_file)
        # The OLD custom parser would have returned "Nz4HdRU". The new
        # parser returns the full hash-bearing value.
        assert parsed["GRAFANA_PASSWORD"] == "Nz4HdRU#not-a-real-password", (
            "F-SCRIPT-002: literal ``#`` in env-value still gets"
            " truncated; check_prod_env.py is using the legacy custom"
            " parser that splits at the first ``#``."
        )

    def test_quoted_value_stripped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('GRAFANA_PASSWORD="quoted-value"\n', encoding="utf-8")
        mod = _load_module()
        parsed = mod.load_env_file(env_file)
        assert parsed["GRAFANA_PASSWORD"] == "quoted-value", (
            "F-SCRIPT-002: parser left wrapping quotes around the value, breaking consumers like json.loads(CORS_ORIGINS)."
        )

    def test_full_line_comment_still_ignored(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# this is a comment\nPLAIN=ok\n", encoding="utf-8")
        mod = _load_module()
        parsed = mod.load_env_file(env_file)
        assert "this is a comment" not in parsed
        assert parsed["PLAIN"] == "ok"
