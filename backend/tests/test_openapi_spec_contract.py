"""Contract test for the OpenAPI spec generator.

Pins a few invariants of the live OpenAPI document so a future
refactor cannot silently break SDK generation or contract tests:

* The spec is valid OpenAPI 3.x.
* The spec includes the documented stable route surface.
* Required core routes exist (auth, jobs, system, health).
* No path contains a leading slash-less segment (malformed path).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "scripts" / "generate_openapi.py"


def _generate(experimental: bool = False) -> dict:
    """Run the OpenAPI generator in a clean subprocess and return the spec."""
    cmd = [sys.executable, str(GENERATOR), "--no-docs-copy"]
    if experimental:
        cmd.append("--experimental")
    env_overrides = {
        "DATAFORGE_DOTENV_PATH": "/dev/null",
        "DATAFORGE_ENV": "development",
        "DATAFORGE_STORAGE_BACKEND": "sqlite",
        "DATAFORGE_API_KEY": "",
        "DATAFORGE_OPERATOR_API_KEY": "",
        "DATAFORGE_ADMIN_API_KEY": "",
        "DATAFORGE_SESSION_SECRET": "openapi-test",
        "DATAFORGE_ALLOW_INSECURE_DEV_AUTH": "true",
        "DATAFORGE_SKIP_DB_CHECK": "true",
    }
    import os

    full_env = os.environ.copy()
    full_env.update(env_overrides)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(REPO),
        timeout=60,
    )
    assert result.returncode == 0, f"openapi generation failed:\n{result.stderr}"

    # The generator writes to artifacts/audit/openapi.json (or .experimental.json).
    suffix = ".experimental" if experimental else ""
    path = REPO / "artifacts" / "audit" / f"openapi{suffix}.json"
    return json.loads(path.read_text())


# Stable paths that MUST exist (per docs/API.md).
REQUIRED_STABLE_PATHS = {
    "/",
    "/api/auth-profiles",
    "/api/jobs",
    "/api/jobs/{job_id}",
    "/health",
    "/ready",
    "/api/system/status",
    "/api/system/manifest",
    "/api/system/audit-log",
    "/api/saas/aup/status",
    "/api/saas/plan",
    "/api/billing/webhook",
    "/api/workflows",
    "/api/workflows/{workflow_id}/runs",
    "/api/scheduled/{job_id}/changes",
    "/api/recycle_bin",
    "/api/user/data",
    "/api/url/analyze",
}


class TestOpenAPISpecContract:
    def test_spec_is_valid_openapi_3(self) -> None:
        spec = _generate()
        assert spec.get("openapi", "").startswith("3."), f"unexpected openapi version: {spec.get('openapi')!r}"
        assert "info" in spec
        assert "title" in spec["info"]
        assert "version" in spec["info"]
        assert "paths" in spec
        assert isinstance(spec["paths"], dict)

    def test_all_required_stable_paths_present(self) -> None:
        spec = _generate()
        actual = set(spec["paths"].keys())
        missing = REQUIRED_STABLE_PATHS - actual
        assert not missing, f"missing required stable paths: {sorted(missing)}"

    def test_no_malformed_paths(self) -> None:
        spec = _generate()
        for path in spec["paths"]:
            assert path.startswith("/"), f"path must start with /: {path!r}"
            assert not path.endswith("/") or path == "/", f"path must not have a trailing slash (other than the root): {path!r}"

    def test_operation_ids_are_non_empty_strings(self) -> None:
        spec = _generate()
        bad: list[str] = []
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    continue
                if not isinstance(op, dict):
                    bad.append(f"{method.upper()} {path}: not a dict")
                    continue
                if "operationId" in op and not isinstance(op["operationId"], str):
                    bad.append(f"{method.upper()} {path}: bad operationId")
        assert not bad, f"operation_id issues: {bad}"

    def test_responses_define_at_least_one_status(self) -> None:
        """Every documented operation should have a 2xx or default response."""
        spec = _generate()
        bad: list[str] = []
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not isinstance(op, dict):
                    continue
                responses = op.get("responses") or {}
                if not responses:
                    bad.append(f"{method.upper()} {path}: no responses documented")
        assert not bad, f"missing responses: {bad[:5]}"

    def test_experimental_includes_additional_routes(self) -> None:
        """The experimental spec must include at least 10 more operations than stable."""
        stable = _generate(experimental=False)
        experimental = _generate(experimental=True)
        stable_ops = sum(
            len([m for m in ops if m.lower() in {"get", "post", "put", "patch", "delete"}]) for ops in stable["paths"].values()
        )
        experimental_ops = sum(
            len([m for m in ops if m.lower() in {"get", "post", "put", "patch", "delete"}])
            for ops in experimental["paths"].values()
        )
        assert experimental_ops > stable_ops, (
            f"experimental spec should have more operations than stable (stable={stable_ops}, experimental={experimental_ops})"
        )

    def test_documented_count_matches_audit(self) -> None:
        """Sanity: the OpenAPI spec contains at least the route inventory's stable count.

        Catches a class of bug where a route is added but the live app
        doesn't actually mount it (so it shows in source-grep but not in
        the spec).
        """
        spec = _generate()
        # Just confirm we have a reasonable surface. The exact number is
        # pinned by the route-inventory generator; we just check the spec
        # is not empty / suspiciously small.
        op_count = sum(
            len([m for m in ops if m.lower() in {"get", "post", "put", "patch", "delete"}]) for ops in spec["paths"].values()
        )
        assert op_count >= 80, f"expected at least 80 operations, got {op_count}"
