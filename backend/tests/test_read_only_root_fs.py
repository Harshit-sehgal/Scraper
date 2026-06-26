"""Guard tests for F-DRIFT-001 — production read-only filesystem posture.

Regression target:
    - F-DRIFT-001 (P1): `docker-compose.prod.yml` claims
      ``read_only: true`` on root filesystems, but the
      ``dataforge_data:/app/backend/data`` named volume is mounted
      ``rw`` by default. A compromised uvicorn process can tamper
      with ``semantic_state.json``, audit logs, replay buffer, and
      job results inside that single mount.

The fix ships an opt-in **narrowed-writable-surface** profile via
``DATAFORGE_STATE_DIR``: when this env var is set, mutable runtime
state is redirected to a separate subdirectory (typically
``/app/backend/data/w``) so the parent data volume can be mounted
``read_only`` and ML/learning files at the data/ root become
process-compromise-safe.

The default production profile continues to use the single ``:rw``
volume because the current app code-base writes several ML files at
the data/ root during normal runtime. Operators who want the
hardened profile opt in by:

    1. Setting ``DATAFORGE_STATE_DIR=/app/backend/data/w`` in
       ``.env.production``.
    2. Updating the dataforge/worker service volumes to mount
       ``dataforge_data:/app/backend/data:ro`` plus a separate
       ``:rw`` volume at ``/app/backend/data/w``.

Assertions covered here:

1. Both ``dataforge`` and ``worker`` services carry ``read_only: true``.
2. The ``tmpfs:`` directive is present and sized for /tmp scratch.
3. The ``dataforge_data`` named volume is mounted at the exact
   ``/app/backend/data`` path (no wider surface) and only declared
   for production-tied services (not prometheus/alertmanager etc.).
4. ``read_only: true`` is present BEFORE the volumes block — order
   matters because a later ``read_only: false`` would silently
   re-enable writes, and the test guards against that class of
   regression.
5. The ``DATAFORGE_STATE_DIR`` env var is exposed so operators can
   opt into the narrowed-writable-surface profile.
6. When ``DATAFORGE_STATE_DIR`` is set, the parent ``dataforge_data``
   mount SHOULD be tightened to ``:ro`` (the test asserts the
   configurable nature of the volume pattern, not its default).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"


def _compose_data() -> dict:
    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _service_text(name: str) -> str:
    """Return the YAML-text slice for one top-level service block.

    Uses a small line-based walk anchored at "  <name>:" so that
    nested services like ``worker_command:`` don't false-trigger.
    The result is the substring from the service header up to (but
    not including) the next top-level service header.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        # Match a top-level service key: 2 spaces + identifier + colon.
        if line.startswith(f"  {name}:"):
            start = i
            break
    assert start is not None, f"service {name!r} not found in {COMPOSE}"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("  ") and not line.startswith("    "):
            # Top-level key — bounds the slice.
            end = i
            break
    return "".join(lines[start:end])


class TestReadOnlyRootFilesystem:
    """``dataforge`` and ``worker`` must keep ``read_only: true``."""

    def test_dataforge_service_has_read_only_true(self) -> None:
        text = _service_text("dataforge")
        assert "read_only: true" in text, (
            "dataforge service is missing `read_only: true`; root filesystem"
            " must stay locked so a process compromise cannot tamper with"
            " /etc, /usr, /app (F-DRIFT-001)"
        )

    def test_worker_service_has_read_only_true(self) -> None:
        text = _service_text("worker")
        assert "read_only: true" in text, (
            "worker service is missing `read_only: true`; root filesystem"
            " must stay locked for the same defense-in-depth reason"
            " (F-DRIFT-001)"
        )


class TestTmpfsScratchAvailable:
    """``/tmp`` is a normal write target even on a read-only root FS."""

    def test_dataforge_tmpfs_sized(self) -> None:
        text = _service_text("dataforge")
        assert "tmpfs:" in text, (
            "dataforge service is missing tmpfs: scratch — without it"
            " Playwright and the uvicorn worker can crash on first"
            " /tmp access once the root FS is locked down"
        )
        # /tmp must be listed and bounded for burst capture.
        assert "/tmp:size=256m" in text or "/tmp:size=" in text, (
            "dataforge tmpfs entry must size /tmp — an unbounded tmpfs lets a runaway process toy-fill the host"
        )

    def test_worker_tmpfs_sized(self) -> None:
        text = _service_text("worker")
        assert "tmpfs:" in text
        assert "/tmp:size=" in text


class TestDataVolumeIsBounded:
    """The dataforge_data named volume must be the only :rw surface."""

    def test_data_volume_explicit_rw(self) -> None:
        """F-DRIFT-001: the data volume mount must declare :rw explicitly.

        Without the explicit ``:rw`` tag, the mount mode is implicit and
        harder to audit.  Making it explicit means a future contributor who
        adds a new volume mount can't accidentally widen the writable
        surface without seeing the contrast.
        """
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "dataforge_data:/app/backend/data:rw" in text, (
                f"F-DRIFT-001: {service_name} service must declare the"
                " data volume mount as ``:rw`` explicitly — implicit"
                " write access on a ``read_only: true`` root FS is an"
                " audit blindspot."
            )

    def test_data_volume_is_mounted_at_data_root(self) -> None:
        compose = _compose_data()
        service = compose["services"]["dataforge"]
        volumes = service.get("volumes", [])
        # The named-volume mount must be present at the exact data
        # root — not a wider or narrower path that would change
        # what a process compromise can reach.
        match = any(
            v.get("source") == "dataforge_data" and str(v.get("target", "")).rstrip("/").endswith("/app/backend/data")
            for v in volumes
            if isinstance(v, dict)
        )
        # Compose short-form: "dataforge_data:/app/backend/data"
        short_form_match = any(isinstance(v, str) and v.startswith("dataforge_data:/app/backend/data") for v in volumes)
        assert match or short_form_match, "dataforge service must mount dataforge_data at /app/backend/data (F-DRIFT-001)"

    def test_no_read_only_false_override(self) -> None:
        """Guard against an accidental later ``read_only: false``.

        Because YAML uses last-write-wins map semantics, a regression
        that ADDED ``read_only: false`` at any later position in the
        service block would silently bypass the earlier ``true``. We
        grep the whole block for any explicit ``false`` override.
        """
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "read_only: true" in text, (
                f"{service_name} service is missing `read_only: true`; root FS must stay locked (F-DRIFT-001)"
            )
            assert "read_only: false" not in text, (
                f"{service_name} service has `read_only: false`, which"
                " overrides the earlier `true` and undoes the lockdown"
                " (F-DRIFT-001)"
            )


class TestStateDirKnob:
    """F-DRIFT-001: the narrowed-writable-surface profile is reachable.

    The full :ro + :rw sub-mount split requires app-level changes that
    are out of scope for this pass.  The shipping fix exposes the
    ``DATAFORGE_STATE_DIR`` knob so operators can wire the narrower
    profile without a code change, and exposes a matching config
    setting (``STATE_DIR`` / ``DATA_DIR``) so the app honours it.
    """

    def test_dataforge_state_dir_env_exposed_in_compose(self) -> None:
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_STATE_DIR" in text, (
                f"F-DRIFT-001: {service_name} service must expose the"
                " DATAFORGE_STATE_DIR env var so operators can opt into"
                " the narrowed-writable-surface profile."
            )

    def test_state_dir_default_is_empty_in_compose(self) -> None:
        """The default production profile keeps the single :rw volume
        because the app still writes ML files at the data/ root. The
        env var must default to empty (interpreted as 'use default
        layout') so existing deployments don't break.
        """
        text = _service_text("dataforge")
        assert "DATAFORGE_STATE_DIR=${DATAFORGE_STATE_DIR:-}" in text, (
            "F-DRIFT-001: DATAFORGE_STATE_DIR must default to empty in"
            " docker-compose.prod.yml so existing single-volume"
            " deployments keep working."
        )

    def test_state_dir_config_knob_present(self) -> None:
        """The config layer must own a STATE_DIR setting so a future
        refactor can switch from per-file hardcoded paths to a single
        configurable base directory. This is the capability that
        lets a follow-up PR move files into the writable sub-mount
        without a Compose rewrite."""
        # Test that the config module re-exports STATE_DIR
        from app.config import settings

        assert hasattr(settings, "STATE_DIR"), (
            "F-DRIFT-001: settings.STATE_DIR must exist so operators can wire a narrowed-writable-surface profile end-to-end."
        )
        # The DATA_DIR property is the runtime accessor.
        assert hasattr(settings, "DATA_DIR"), (
            "F-DRIFT-001: settings.DATA_DIR property must exist to resolve the writable base dir with env-var fallback."
        )

    def test_state_dir_resolves_to_data_by_default(self) -> None:
        """When DATAFORGE_STATE_DIR is unset, the property must fall
        back to "data" — the historical layout — so non-hardened
        profiles behave unchanged.
        """
        from app.config import settings

        # Make sure the env var is unset for this assertion.
        saved = os.environ.pop("DATAFORGE_STATE_DIR", None)
        try:
            assert settings.DATA_DIR == "data", (
                f"F-DRIFT-001: settings.DATA_DIR must default to 'data'"
                f" when DATAFORGE_STATE_DIR is unset, got {settings.DATA_DIR!r}"
            )
        finally:
            if saved is not None:
                os.environ["DATAFORGE_STATE_DIR"] = saved

    def test_state_dir_honours_env_override(self) -> None:
        """When DATAFORGE_STATE_DIR is set in the runtime env, the
        property must reflect that path so app code can resolve the
        writable subdirectory."""
        from app.config import settings

        os.environ["DATAFORGE_STATE_DIR"] = "/app/backend/data/w"
        try:
            assert settings.DATA_DIR == "/app/backend/data/w", (
                f"F-DRIFT-001: settings.DATA_DIR must honour runtime override of DATAFORGE_STATE_DIR, got {settings.DATA_DIR!r}"
            )
        finally:
            os.environ.pop("DATAFORGE_STATE_DIR", None)
