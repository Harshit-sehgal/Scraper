"""Guard tests for F-DOCKER-005 — production image tag pinning.

Regression target:
    - F-DOCKER-005 (P1): mutable ``:latest`` default for the dataforge
      and worker services defeats the Dockerfile's pinned-digest model
      (Dockerfile:14-16) and lets a registry swap pull a different image
      on every ``docker compose -f docker-compose.prod.yml up -d``.
      Production deploys must use an immutable tag, derived from
      ``DATAFORGE_IMAGE_TAG``.

This module inspects ``docker-compose.prod.yml``, the ``Makefile`` prod
target, and ``scripts/check_prod_env.py`` as text. No Docker daemon
required (matches the AGENTS.md rule 1 quick-gate discipline).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
MAKEFILE = REPO_ROOT / "Makefile"
ENV_CHECK = REPO_ROOT / "scripts" / "check_prod_env.py"
ENV_EXAMPLE = REPO_ROOT / ".env.production.example"


def _compose_text() -> str:
    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    return COMPOSE.read_text(encoding="utf-8")


def _compose_data() -> dict:
    return yaml.safe_load(_compose_text())


def _makefile_text() -> str:
    assert MAKEFILE.is_file(), f"missing {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


def _env_check_text() -> str:
    assert ENV_CHECK.is_file(), f"missing {ENV_CHECK}"
    return ENV_CHECK.read_text(encoding="utf-8")


class TestProdComposeRejectsLatestTag:
    """``dataforge`` and ``worker`` images must require an explicit tag."""

    def test_dataforge_image_requires_tag(self) -> None:
        image_line = _compose_data()["services"]["dataforge"]["image"]
        # The image reference must consume a non-empty, non-``latest`` tag.
        # We accept either ``dataforge:${DATAFORGE_IMAGE_TAG:?...}`` (the
        # strict required-or-fail form) or any explicit tag other than
        # ``latest``. The literal fallback ``${...:-latest}`` is the bug.
        assert ":-latest" not in image_line, f"dataforge image line still has a :-latest fallback: {image_line!r}"
        assert "${DATAFORGE_IMAGE_TAG:?}" in image_line or (
            "DATAFORGE_IMAGE_TAG" in image_line and "${DATAFORGE_IMAGE_TAG" in image_line
        ), f"dataforge image must reference ${{DATAFORGE_IMAGE_TAG}} (got: {image_line!r})"

    def test_worker_image_requires_tag(self) -> None:
        image_line = _compose_data()["services"]["worker"]["image"]
        assert ":-latest" not in image_line, f"worker image line still has a :-latest fallback: {image_line!r}"
        assert "${DATAFORGE_IMAGE_TAG:?}" in image_line or (
            "DATAFORGE_IMAGE_TAG" in image_line and "${DATAFORGE_IMAGE_TAG" in image_line
        ), f"worker image must reference ${{DATAFORGE_IMAGE_TAG}} (got: {image_line!r})"


class TestMakefileProdUsesPullNever:
    """The ``prod`` target must pin image pulls and require a tag."""

    def test_prod_target_passes_pull_never(self) -> None:
        text = _makefile_text()
        # Find the ``prod:`` target body — every line until the next
        # blank line / next target header. This is a small textual scan,
        # not a full Makefile parser, which is enough for the assertion.
        m = re.search(
            r"^prod:\s*[^\n]*\n(?P<body>(?:^[ \t]+.+\n)+)",
            text,
            re.MULTILINE,
        )
        assert m is not None, "Makefile has no `prod:` target"
        body = m.group("body")
        assert "--pull=never" in body, (
            "Makefile `prod` target must pass --pull=never so a registry swap cannot silently re-pull a different image"
        )

    def test_prod_target_checks_image_tag(self) -> None:
        text = _makefile_text()
        m = re.search(
            r"^prod:\s*[^\n]*\n(?P<body>(?:^[ \t]+.+\n)+)",
            text,
            re.MULTILINE,
        )
        assert m is not None, "Makefile has no `prod:` target"
        body = m.group("body")
        # The target must refuse to start without DATAFORGE_IMAGE_TAG.
        # We accept either a shell guard (``test -n "$$DATAFORGE_IMAGE_TAG"``)
        # or an explicit error / fail-fast pattern.
        assert "DATAFORGE_IMAGE_TAG" in body, (
            "Makefile `prod` target must reference DATAFORGE_IMAGE_TAG so"
            " operators see a missing-tag failure instead of a silent default"
        )


class TestEnvValidatorRequiresImageTag:
    """``check_prod_env.py`` must require a non-latest tag in production."""

    def test_image_tag_in_required_checks(self) -> None:
        text = _env_check_text()
        # The required-vars list is the long tuple-list in ``main()``.
        # We accept either ``DATAFORGE_IMAGE_TAG`` appearing as a
        # standalone entry or a validator named ``check_image_tag``.
        assert "DATAFORGE_IMAGE_TAG" in text, "check_prod_env.py must require DATAFORGE_IMAGE_TAG in production"

    def test_image_tag_validator_rejects_latest(self) -> None:
        text = _env_check_text()
        # Greppable: there must be a check that ``latest`` is rejected.
        # We assert the literal ``"latest"`` token appears near
        # ``DATAFORGE_IMAGE_TAG`` to allow either an ``==``/``!=``/``in``
        # comparison or a literal list of forbidden values.
        # The test is loose on whitespace so the validator can be
        # either a function body or a one-liner.
        m = re.search(
            r"def\s+check_image_tag\b[^\n]*:\s*\n(?P<body>(?:\s{4,}.*\n)+)",
            text,
        )
        assert m is not None, (
            "check_prod_env.py: missing check_image_tag() function. F-DOCKER-005"
            " requires an explicit validator for the production image tag."
        )
        body = m.group("body")
        assert "latest" in body, "check_image_tag() must explicitly reject the 'latest' tag"


class TestEnvExampleDocumentsTag:
    """``.env.production.example`` must include DATAFORGE_IMAGE_TAG."""

    def test_env_example_has_image_tag(self) -> None:
        assert ENV_EXAMPLE.is_file(), f"missing {ENV_EXAMPLE}"
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        assert "DATAFORGE_IMAGE_TAG" in text, ".env.production.example must document DATAFORGE_IMAGE_TAG"
        assert "latest" not in text or "#" in text.split("latest", 1)[0][-50:], (
            ".env.production.example must not suggest 'latest' as a value"
        )
