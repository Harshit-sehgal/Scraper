"""Guard tests for the Docker dev / production split.

These tests inspect the Dockerfile and compose files as text. They
are deliberately language-agnostic so a missing Docker daemon does
not block the suite (the AGENTS.md rule 1 quick gate runs without
Docker locally).

Regression targets:
    - F-DOCKER-001 (P0): default ``docker compose up`` should not pass
      ``--reload`` or ``--log-level debug`` — the dev hot-reload is
      opt-in via ``DATAFORGE_ENABLE_RELOAD`` (and the override file).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests/X.py → repo root
DOCKERFILE = REPO_ROOT / "Dockerfile"
DEV_COMPOSE = REPO_ROOT / "docker-compose.override.yml"
BASE_COMPOSE = REPO_ROOT / "docker-compose.yml"
MAKEFILE = REPO_ROOT / "Makefile"


def _dockerfile_text() -> str:
    assert DOCKERFILE.is_file(), f"missing {DOCKERFILE}"
    return DOCKERFILE.read_text(encoding="utf-8")


def _dev_stage_block(text: str) -> str:
    """Return the text between ``FROM deps AS dev`` and the next ``FROM``."""
    m = re.search(r"FROM\s+deps\s+AS\s+dev\b(.*?)(?=^FROM\s|\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, "expected a dev stage in the Dockerfile"
    return m.group(1)


def _base_compose_text() -> str:
    assert BASE_COMPOSE.is_file(), f"missing {BASE_COMPOSE}"
    return BASE_COMPOSE.read_text(encoding="utf-8")


def _base_compose() -> dict:
    return yaml.safe_load(_base_compose_text())


def _dev_override_text() -> str:
    assert DEV_COMPOSE.is_file(), f"missing {DEV_COMPOSE}"
    return DEV_COMPOSE.read_text(encoding="utf-8")


def _makefile_text() -> str:
    assert MAKEFILE.is_file(), f"missing {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# F-DOCKER-001 — dev reload must be gated
# ---------------------------------------------------------------------------


class TestDevReloadGating:
    """The dev stage's uvicorn reload/--log-level debug is opt-in.

    Regression: prior to the fix the dev stage CMD unconditionally
    passed ``--reload --log-level debug`` and the base compose wired
    the dev target by default. A fresh ``docker compose up`` therefore
    attached a debug-logging, hot-reloaded backend to the host tree.
    """

    def test_dev_stage_does_not_pass_reload_by_default(self) -> None:
        body = _dev_stage_block(_dockerfile_text())
        # The dev stage must reference the env-var gate, not --reload
        # unconditionally. Look for the shell wrapper that branches on
        # DATAFORGE_ENABLE_RELOAD.
        assert "DATAFORGE_ENABLE_RELOAD" in body, "Dockerfile dev stage no longer gates --reload on the env var"
        # Direct uvicorn invocation without the gate must not appear
        # alongside the reload flag.
        direct_violation = re.search(
            r'CMD\s+\[?["\']uvicorn[^"\']*--reload[^"\']*["\']',
            body,
        )
        assert not direct_violation, "Dockerfile dev stage still runs uvicorn with --reload unconditionally"

    def test_base_compose_does_not_default_to_dev_target(self) -> None:
        text = _base_compose_text()
        # The base compose must NOT pin target: dev. The dev target is
        # opt-in via the override file.
        bad = re.search(r"^\s*target:\s*dev\s*$", text, re.MULTILINE)
        assert not bad, "docker-compose.yml still targets the dev stage by default"

    def test_dev_override_opts_into_dev_target_and_reload(self) -> None:
        """The override is the only path that enables hot-reload.

        Without the override, the base compose ships ``target:
        production`` and the dev CMD's reload branch never fires. The
        override must therefore explicitly set ``target: dev`` and
        ``DATAFORGE_ENABLE_RELOAD=1`` so the dev workflow is still
        reachable.
        """
        text = _dev_override_text()
        assert "target: dev" in text, "docker-compose.override.yml no longer switches to dev target"
        assert "DATAFORGE_ENABLE_RELOAD" in text, "docker-compose.override.yml no longer opts in to uvicorn --reload"


# ---------------------------------------------------------------------------
# F-DOCKER-002 — dev bind mounts must use the host UID/GID
# ---------------------------------------------------------------------------


class TestDevBindMountOwnership:
    """The dev service should not write root/image-owned files into host mounts."""

    def test_base_compose_runs_service_with_host_uid_gid_placeholders(self) -> None:
        service = _base_compose()["services"]["dataforge"]
        assert service.get("user") == "${DATAFORGE_DEV_UID:-1000}:${DATAFORGE_DEV_GID:-1000}"

    def test_makefile_passes_host_uid_gid_to_compose(self) -> None:
        text = _makefile_text()
        assert "DATAFORGE_DEV_UID ?= $(shell id -u" in text
        assert "DATAFORGE_DEV_GID ?= $(shell id -g" in text
        assert "DATAFORGE_DEV_UID=$(DATAFORGE_DEV_UID)" in text
        assert "DATAFORGE_DEV_GID=$(DATAFORGE_DEV_GID)" in text

    def test_dev_compose_does_not_overlay_backend_data_with_image_owned_volume(self) -> None:
        compose = _base_compose()
        volumes = compose["services"]["dataforge"].get("volumes", [])
        assert "dataforge_data:/app/backend/data" not in volumes
        assert "dataforge_data" not in compose.get("volumes", {})


# ---------------------------------------------------------------------------
# Production stage must not regress
# ---------------------------------------------------------------------------


class TestProdStageStillProductionSafe:
    """The production stage CMD stays untouched by the dev-reload fix."""

    def test_production_stage_cmd_does_not_pass_reload(self) -> None:
        text = _dockerfile_text()
        # Find the production stage block; the CMD there is a script,
        # not uvicorn-with-reload.
        m = re.search(
            r"FROM\s+deps\s+AS\s+production\b(.*?)\bCMD\s+(?P<cmd>\[[^\]]+\]|[^\n]+)\s*\n",
            text,
            re.DOTALL,
        )
        assert m, "production stage CMD not found"
        cmd = m.group("cmd")
        assert "--reload" not in cmd, "production stage CMD must not include --reload"
        assert "--log-level debug" not in cmd, "production stage CMD must not include --log-level debug"
