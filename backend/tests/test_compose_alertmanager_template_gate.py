"""Drift guard for F-DOCKER-008 — alertmanager template substitution gate.

Regression target:
    - F-DOCKER-008 (P2): ``docker-compose.override.local.yml`` (local)
      used a broader ``__ALERTMANAGER_`` prefix in its leftover-template
      grep gate than ``docker-compose.prod.yml`` (which lists each
      specific name). When a new ``__ALERTMANAGER_NEW__`` placeholder
      is added, the local override silently passes while the production
      grep would catch it — so the production stack silently starts
      with an unreplaced token in ``alertmanager.yml``.

Lock-in: both files must declare the same exact list of template
placeholders. The test grep-decodes the substitution group from each
file and asserts byte-equality of the placeholder list, so any pair
that drifts triggers a CI failure at the moment of authoring.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_OVERRIDE = REPO_ROOT / "docker-compose.override.local.yml"
PROD_COMPOSE = REPO_ROOT / "docker-compose.prod.yml"

# Captures a sequence of `__ALERTMANAGER_<NAME>__` tokens separated by `\|`
# in the single-quoted argument of a `grep -q` invocation. Note the YAML
# pipe `\|` is a literal in the source, but in the Python regex we need
# `\\|` (raw: `\\|`) so it matches: the source contains **`\|`** as two
# characters, which Python regex interprets as escaped `|`-or and
# accepts both with or without the backslash. We accept either form so
# future YAML quoting changes don't regress the test.
_PLACEHOLDER_LIST_RE = re.compile(
    r"grep\s+-q[^\n]*?'((?:__ALERTMANAGER_(?:[A-Z0-9_]+__(?:\\?\|))+__ALERTMANAGER_[A-Z0-9_]+__))'",
    flags=re.MULTILINE,
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _placeholder_set_from_grep(text: str) -> set[str]:
    """Pull every `__ALERTMANAGER_*__` token listed in the grep gate."""
    out: set[str] = set()
    for m in _PLACEHOLDER_LIST_RE.finditer(text):
        body = m.group(1)
        # The captured body is `__A__|__B__|__C__`. Split and normalize.
        for token in body.split(r"\|"):
            t = token.strip()
            if t.startswith("__ALERTMANAGER_") and t.endswith("__"):
                out.add(t)
    return out


class TestAlertmanagerTemplateGateInSync:
    """Both compose files must detect the same set of leftover placeholders."""

    def test_both_compose_files_use_named_list(self) -> None:
        """Neither file can rely on the broad ``__ALERTMANAGER_`` prefix or a stub."""
        local_text = _read(LOCAL_OVERRIDE)
        prod_text = _read(PROD_COMPOSE)

        # The broad-prefix form would still match a single underscore-wildcard __ALERTMANAGER_.
        # We require at least two named placeholders in each grep so the substitution gate
        # is meaningful and matches all possible placeholder names.
        local_set = _placeholder_set_from_grep(local_text)
        prod_set = _placeholder_set_from_grep(prod_text)
        assert len(local_set) >= 2, (
            f"{LOCAL_OVERRIDE}: alertmanager grep gate is too narrow or uses a wildcard placeholder (found: {sorted(local_set)})"
        )
        assert len(prod_set) >= 2, (
            f"{PROD_COMPOSE}: alertmanager grep gate is too narrow or uses a wildcard placeholder (found: {sorted(prod_set)})"
        )

    def test_placeholder_lists_byte_identical(self) -> None:
        """The two grep gates must list the exact same placeholder names.

        Drift between dev and prod lets ``docker-compose.override.local.yml``
        silently pass while production fails (or vice versa). The test asserts
        set-equality so order/whitespace differences don't matter, but any
        missing or extra placeholder trips CI.
        """
        local_text = _read(LOCAL_OVERRIDE)
        prod_text = _read(PROD_COMPOSE)
        local_set = _placeholder_set_from_grep(local_text)
        prod_set = _placeholder_set_from_grep(prod_text)
        difference_left = local_set - prod_set
        difference_right = prod_set - local_set
        assert not difference_left and not difference_right, (
            f"alertmanager template-substitution grep gate drifts between"
            " docker-compose.override.local.yml and docker-compose.prod.yml:"
            f"\n  in local-only: {sorted(difference_left)}"
            f"\n  in prod-only:  {sorted(difference_right)}"
            f"\nF-DOCKER-008: any new __ALERTMANAGER_*__ placeholder must"
            " be added to BOTH gates in the same change."
        )


class TestAlertmanagerSubstitutionsCoverPlaceholders:
    """Every placeholder listed in the gate must also appear in the sed-e chain.

    Catches the inverse bug: a placeholder is in the gate but missing from
    the substitution list, so the gate can never fire (false negative).
    """

    def test_each_gated_placeholder_is_substituted(self) -> None:
        for path in (LOCAL_OVERRIDE, PROD_COMPOSE):
            text = _read(path)
            gated = _placeholder_set_from_grep(text)
            for placeholder in gated:
                # sed syntax: `s|__ALERTMANAGER_FOO__|...|g`. The literal
                # token with both ``__`` ends must appear inside a sed `'s|...'`
                # expression or substitution silently fails.
                sed_pattern = f"|{placeholder}|"
                assert sed_pattern in text, (
                    f"{path}: gated placeholder {placeholder} does not appear"
                    " in any `sed -e 's|...|...|'` substitution chain. F-DOCKER-008:"
                    " add the corresponding substitution or remove it from the grep gate."
                )
