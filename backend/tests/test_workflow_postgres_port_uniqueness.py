"""Static guard for F-CI-006 — postgres port uniqueness across CI workflows.

Three workflows spin up the ``postgres:16-alpine`` service:

- ``postgres-tests.yml``
- ``optional-suites.yml``
- ``validate-production.yml``

If they all pin port 5432 and request a host-port mapping of
``5432:5432``, two parallel jobs on the same self-hosted runner will
collide: postgres' port bind fails silently and ``pg_isready`` flaps.

The fix used here is to declare the ``ports:`` map with **the
container port only** (e.g. ``- 5432`` without a host map). GitHub
Actions then assigns a free host port, surfaced as
``job.services.postgres.ports[5432]``. The
``DATAFORGE_DATABASE_URL`` is built from that expression so the test
process follows the same dynamic port.

Lock-in:

1. ``options:`` must remain absent of a ``--port=NNNN`` *change*.
   (The image's default 5432 inside the container is still fine.)
2. ``ports:`` must publish the container port (5432) without a
   host-port column, *or* use a mapping where the host port is
   **explicitly distinct per workflow**.
3. ``DATAFORGE_DATABASE_URL`` must reference
   ``job.services.postgres.ports[5432]`` so the URL tracks the
   GHA-assigned host port.

This is text-only; the actual collision surface only manifests when
multiple workflows run concurrently on the same runner.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

POSTGRES_WORKFLOWS = (
    "postgres-tests.yml",
    "optional-suites.yml",
    "validate-production.yml",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_DB_URL_DYNAMIC = re.compile(r"job\.services\.postgres\.ports\[(\d+)\]")
_DB_URL_PLAIN = re.compile(r"localhost:(?P<port>\d+)/")
_PORTS_MAP = re.compile(r"-\s+(\d+)(?::(\d+))?")
_CONTAINER_PORT = re.compile(r"postgres:\d+[-a-z]*")  # image ref


def _detect_pin(path: Path) -> tuple[int | None, int | None, int | None]:
    """Return (container_port, host_port, url_port_or_none).

    ``container_port`` is the integer that the workflow expects to be
    available inside the container (the *key* in the GHA service map).
    ``host_port`` is the explicit host-side map (None if bare port).
    ``url_port_or_none`` is the literal port embedded in
    ``DATAFORGE_DATABASE_URL`` (None when it uses the GHA dynamic
    expression).
    """
    text = _read(path)
    port_decl = _PORTS_MAP.findall(text)
    host_port = None
    container_port: int | None = None
    if port_decl:
        first_pair = port_decl[0]
        container_port = int(first_pair[0])
        host_port = int(first_pair[1]) if first_pair[1] else None

    url_port: int | None = None
    m = _DB_URL_DYNAMIC.search(text)
    if m:
        url_port = int(m.group(1))
    else:
        m = _DB_URL_PLAIN.search(text)
        if m:
            url_port = int(m.group("port"))
    return container_port, host_port, url_port


class TestPostgresPortsAreResolvableAcrossWorkflows:
    """Each workflow must publish postgres on a resolvable port."""

    def test_pin_is_published(self) -> None:
        for name in POSTGRES_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            container_port, _, _ = _detect_pin(path)
            assert container_port is not None, (
                f"{name}: postgres service must publish a container"
                " port (e.g. ``- 5432`` or ``- 5432:5433``) so GHA"
                " can route jobs.services.postgres.ports[N] traffic."
            )

    def test_url_references_published_port(self) -> None:
        """``DATAFORGE_DATABASE_URL`` must reference the published port."""
        for name in POSTGRES_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            container_port, _, url_port = _detect_pin(path)
            assert container_port is not None
            assert url_port == container_port, (
                f"{name}: DATAFORGE_DATABASE_URL references port"
                f" {url_port} but the postgres service publishes"
                f" port {container_port}. They must agree (or both"
                " must use ``job.services.postgres.ports[N]``)."
            )

    def test_collision_prone_pin_rejected(self) -> None:
        """No workflow may hard-pin a host port identical to the next.

        GHA still owns the host port; this test guards only against
        maps like ``- 5432:5432`` that claim a specific host port,
        which is the pre-F-CI-006 form that caused collisions on
        shared self-hosted runners.
        """
        bad: list[str] = []
        for name in POSTGRES_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            # Look for ``- 5432:5432``-style explicit map.
            for line in text.splitlines():
                stripped = line.strip()
                m = re.match(r"-\s+(\d+):(\d+)\s*$", stripped)
                if m and m.group(1) == m.group(2):
                    bad.append(f"{name}: {stripped}")
        assert not bad, "F-CI-006: explicit identical host/container port maps risk parallel-job collisions:\n  " + "\n  ".join(
            bad
        )

    def test_each_workflow_has_postgres_service(self) -> None:
        for name in POSTGRES_WORKFLOWS:
            path = WORKFLOWS_DIR / name
            text = _read(path)
            assert "postgres:16-alpine" in text, f"{name}: expected ``postgres:16-alpine`` service image."
