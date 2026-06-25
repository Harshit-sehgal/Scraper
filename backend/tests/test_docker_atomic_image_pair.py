"""Guard tests for F-DRIFT-002 — atomic app/worker image pairing in production.

Regression target:
    - F-DRIFT-002 (P3): ``dataforge`` and ``worker`` services share the
      same ``DATAFORGE_IMAGE_TAG`` template, but local rebuilds of just
      one service would still create a split-brain rollout — the dataforge
      container would write a state shape produced by image v2 while the
      worker would still execute v1's loader. Operators who ``docker
      compose build worker`` (without rebuilding ``dataforge``) bypass the
      release pipeline's atomic-publish guarantee.

Lock-in: both services must reference the *same* ``DATAFORGE_IMAGE_TAG``
variable in their ``image:`` directive. The test is intentionally
structural — textual regex over the rendered compose — so it survives
the fix without coupling to YAML schema details.

This is a complement to F-DOCKER-005 (which pins the tag) and uses the
same text-only invariant philosophy as ``test_docker_image_tag_pinning``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"


def _compose_text() -> str:
    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    return COMPOSE.read_text(encoding="utf-8")


def _compose_data() -> dict:
    return yaml.safe_load(_compose_text())


class TestAtomicImagePair:
    """``dataforge`` and ``worker`` must consume the same production image tag."""

    def test_both_services_exist(self) -> None:
        services = _compose_data()["services"]
        assert "dataforge" in services, "production compose missing `dataforge` service"
        assert "worker" in services, "production compose missing `worker` service"

    def test_both_services_consume_dataforge_image_tag(self) -> None:
        """Both dataforge and worker services must reference ${DATAFORGE_IMAGE_TAG}."""
        data = _compose_data()
        for name in ("dataforge", "worker"):
            image = data["services"][name]["image"]
            assert "DATAFORGE_IMAGE_TAG" in image, (
                f"production compose service `{name}` image: must reference ${{DATAFORGE_IMAGE_TAG}}"
                f" so the same artifact is published atomically (got: {image!r})"
            )

    def test_shared_image_reference_is_byte_identical(self) -> None:
        """The image directive bytes must match exactly so they always pull the same digest.

        A drift like ``dataforge:${DATAFORGE_IMAGE_TAG}`` vs
        ``dataforge:${DATAFORGE_IMAGE_TAG}-amd64`` would silently desync
        the two services on multi-arch images. Greppable invariant.
        """
        data = _compose_data()
        dataforge_img = data["services"]["dataforge"]["image"]
        worker_img = data["services"]["worker"]["image"]
        assert dataforge_img == worker_img, (
            f"dataforge/worker image refs diverge in docker-compose.prod.yml: "
            f"dataforge={dataforge_img!r} worker={worker_img!r}. "
            "Both services must share the exact same image reference to guarantee an atomic deploy."
        )

    def test_no_alternate_image_set(self) -> None:
        """Neither service may silently override ``image:`` per-build.

        The CI release pipeline relies on the operator pulling a single
        shared tag. If a service conditionally overrides ``image:`` based
        on local-state, the atomic-pair guarantee breaks locally.
        """
        text = _compose_text()
        # The only acceptable image reference uses ${DATAFORGE_IMAGE_TAG}.
        # If a future change adds another ``dataforge:`` literal (e.g. for
        # a sidecar override), this test fails before the drift reaches CI.
        bad = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("image:") and "dataforge:" in stripped and "DATAFORGE_IMAGE_TAG" not in stripped:
                bad.append(stripped)
        # Allow non-dataforge images (postgres, prometheus, etc.).
        # The check filters only lines like ``image: dataforge:<other-tag>``.
        bad = [b for b in bad if "dataforge:" in b and "${DATAFORGE_IMAGE_TAG" not in b]
        assert not bad, (
            "docker-compose.prod.yml contains a `dataforge:` image line that does not reference "
            f"${{DATAFORGE_IMAGE_TAG}}: {bad}. This would break the F-DRIFT-002 atomic-pair guarantee."
        )


class TestBuildContextShared:
    """Both services must build from the same context + Dockerfile + target."""

    def test_dataforge_and_worker_share_build_target(self) -> None:
        data = _compose_data()
        for name in ("dataforge", "worker"):
            build = data["services"][name].get("build")
            assert build is not None, f"production compose service `{name}` must declare a build section"
            assert build.get("dockerfile") == "Dockerfile", (
                f"production compose service `{name}` must build from ./Dockerfile (got: {build.get('dockerfile')!r})"
            )
            assert build.get("target") == "production", (
                f"production compose service `{name}` must declare `target: production`"
                f" so both services ship the same compiled artifact (got: {build.get('target')!r})"
            )

    def test_dataforge_and_worker_share_build_context(self) -> None:
        data = _compose_data()
        for name in ("dataforge", "worker"):
            build = data["services"][name].get("build")
            assert build is not None, f"production compose service `{name}` must declare a build section"
            ctx = build.get("context")
            assert ctx in (None, ".", "./"), (
                f"production compose service `{name}` build.context must be the repo root"
                f" so both services build from identical source (got: {ctx!r})"
            )
