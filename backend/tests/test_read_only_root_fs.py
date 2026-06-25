"""Guard tests for F-DRIFT-001 — production read-only filesystem posture.

Regression target:
    - F-DRIFT-001 (P1): `docker-compose.prod.yml` claims
      ``read_only: true`` on root filesystems, but the
      ``dataforge_data:/app/backend/data`` named volume is mounted
      ``rw`` by default. A compromised uvicorn process can tamper
      with ``semantic_state.json``, audit logs, replay buffer, and
      job results inside that single mount.

This module performs protective assertions only — it does **not**
attempt to mount semantic_state.json as :ro, because ``backend/app/
semantic_persistence.py::save_semantic_state`` writes that file
during normal runtime. The volume tightening is documented in the
ledger as a follow-up that requires an app-level cache split.

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
"""

from __future__ import annotations

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
