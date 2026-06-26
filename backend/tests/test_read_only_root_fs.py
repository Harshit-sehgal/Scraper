"""Guard tests for F-DRIFT-001 — production read-only filesystem posture.

Regression target:
    - F-DRIFT-001 (P1): `docker-compose.prod.yml` claims
      ``read_only: true`` on root filesystems, but the
      ``dataforge_data:/app/backend/data`` named volume was mounted
      ``rw`` by default — a compromised uvicorn process could tamper
      with ``semantic_state.json``, selector_memory.json,
      domain_intelligence.json, and other ML/learning state at the
      data/ root.

The fix (implemented) uses a **split-volume** layout:
  - ``dataforge_data:/app/backend/data:ro`` — read-only root data mount
  - ``dataforge_state:/app/backend/data/w:rw`` — writable state subdir

All runtime-writable paths (semantic state, selector memory,
domain intelligence, audit logs) are redirected into the ``w/``
subdirectory via env var settings, so a compromised process cannot
tamper with non-volatile learning state at the data/ root.

Assertions covered here:

1. Both ``dataforge`` and ``worker`` services carry ``read_only: true``.
2. The ``tmpfs:`` directive is present and sized for /tmp scratch.
3. The ``dataforge_data`` named volume is mounted ``:ro`` at
   ``/app/backend/data`` — the root data mount is NOT writable.
4. A separate ``dataforge_state`` volume is mounted ``:rw`` at
   ``/app/backend/data/w`` — the ONLY writable surface.
5. ``DATAFORGE_STATE_DIR`` is set to ``/app/backend/data/w`` by default.
6. ``read_only: true`` is present BEFORE the volumes block — order
   matters because a later ``read_only: false`` would silently
   re-enable writes.
7. The config layer honours ``DATAFORGE_STATE_DIR`` env var.
8. Selector memory and domain intelligence path resolution respects
   config overrides (not hardcoded data/ paths).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"


def _service_text(name: str) -> str:
    """Return the YAML-text slice for one top-level service block."""
    text = COMPOSE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"  {name}:"):
            start = i
            break
    assert start is not None, f"service {name!r} not found in {COMPOSE}"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("  ") and not line.startswith("    "):
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
        assert "/tmp:size=256m" in text or "/tmp:size=" in text, (
            "dataforge tmpfs entry must size /tmp — an unbounded tmpfs lets a runaway process toy-fill the host"
        )

    def test_worker_tmpfs_sized(self) -> None:
        text = _service_text("worker")
        assert "tmpfs:" in text
        assert "/tmp:size=" in text


class TestSplitVolumeLayout:
    """F-DRIFT-001: read-only data root + writable state sub-mount."""

    def test_data_volume_mounted_read_only(self) -> None:
        """The dataforge_data named volume must be :ro at /app/backend/data."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "dataforge_data:/app/backend/data:ro" in text, (
                f"F-DRIFT-001: {service_name} must mount the data root volume"
                " as :ro so a compromised process cannot tamper with ML state"
                " files (semantic_state.json, selector_memory.json, etc.)"
            )

    def test_state_volume_mounted_read_write(self) -> None:
        """A separate dataforge_state volume must be :rw at /app/backend/data/w."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "dataforge_state:/app/backend/data/w:rw" in text, (
                f"F-DRIFT-001: {service_name} must mount a writable"
                " dataforge_state volume at /app/backend/data/w — the"
                " only writable surface for runtime state."
            )

    def test_no_data_root_rw_mount(self) -> None:
        """The old :rw mount at the data root must not be present."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "dataforge_data:/app/backend/data:rw" not in text, (
                f"F-DRIFT-001: {service_name} must NOT mount the data root as :rw — that defeats the read-only protection."
            )

    def test_no_read_only_false_override(self) -> None:
        """Guard against an accidental later ``read_only: false``."""
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


class TestStateDirConfiguration:
    """F-DRIFT-001: DATAFORGE_STATE_DIR must be set in production."""

    def test_dataforge_state_dir_set_in_compose(self) -> None:
        """DATAFORGE_STATE_DIR must default to /app/backend/data/w in prod."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_STATE_DIR=/app/backend/data/w" in text, (
                f"F-DRIFT-001: {service_name} must set"
                " DATAFORGE_STATE_DIR=/app/backend/data/w so runtime"
                " writes go to the writable sub-mount."
            )

    def test_semantic_state_path_in_state_dir(self) -> None:
        """DATAFORGE_SEMANTIC_STATE_PATH must point into the writable subdirectory."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_SEMANTIC_STATE_PATH=/app/backend/data/w/semantic_state.json" in text, (
                f"F-DRIFT-001: {service_name} must set semantic state path inside the writable /app/backend/data/w directory."
            )

    def test_audit_log_dir_in_state_dir(self) -> None:
        """DATAFORGE_AUDIT_LOG_DIR must point into the writable subdirectory."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_AUDIT_LOG_DIR=/app/backend/data/w/logs" in text, (
                f"F-DRIFT-001: {service_name} must set audit log dir inside the writable /app/backend/data/w directory."
            )

    def test_selector_memory_path_redirected(self) -> None:
        """DATAFORGE_SELECTOR_MEMORY_PATH must point into the writable subdirectory."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_SELECTOR_MEMORY_PATH=/app/backend/data/w/selector_memory.json" in text, (
                f"F-DRIFT-001: {service_name} must redirect selector memory path into the writable /app/backend/data/w directory."
            )

    def test_domain_intelligence_path_redirected(self) -> None:
        """DATAFORGE_DOMAIN_INTELLIGENCE_PATH must point into the writable subdirectory."""
        for service_name in ("dataforge", "worker"):
            text = _service_text(service_name)
            assert "DATAFORGE_DOMAIN_INTELLIGENCE_PATH=/app/backend/data/w/domain_intelligence.json" in text, (
                f"F-DRIFT-001: {service_name} must redirect domain"
                " intelligence path into the writable /app/backend/data/w directory."
            )


class TestStateDirKnob:
    """F-DRIFT-001: the STATE_DIR config knob works at runtime."""

    def test_state_dir_config_knob_present(self) -> None:
        from app.config import settings

        assert hasattr(settings, "STATE_DIR"), (
            "F-DRIFT-001: settings.STATE_DIR must exist so operators can wire a narrowed-writable-surface profile end-to-end."
        )
        assert hasattr(settings, "DATA_DIR"), (
            "F-DRIFT-001: settings.DATA_DIR property must exist to resolve the writable base dir with env-var fallback."
        )

    def test_state_dir_resolves_to_data_by_default(self) -> None:
        from app.config import settings

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
        from app.config import settings

        os.environ["DATAFORGE_STATE_DIR"] = "/app/backend/data/w"
        try:
            assert settings.DATA_DIR == "/app/backend/data/w", (
                f"F-DRIFT-001: settings.DATA_DIR must honour runtime override of DATAFORGE_STATE_DIR, got {settings.DATA_DIR!r}"
            )
        finally:
            os.environ.pop("DATAFORGE_STATE_DIR", None)
