"""Regression guard for F-CI-006 Postgres service port mapping.

GitHub Actions jobs in this repository run directly on the runner, so
Postgres service containers need a host port. Mapping ``5432:5432`` is
fragile on shared/self-hosted runners because concurrent workflows can
race for the same host port. The documented collision-safe form is to
publish only the container port and read the assigned host port from
``job.services.postgres.ports[5432]`` inside the test step.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

POSTGRES_WORKFLOWS = (
    "optional-suites.yml",
    "postgres-tests.yml",
    "validate-production.yml",
)

RANDOM_PORT_CONTEXT = "${{ job.services.postgres.ports[5432] }}"


def _workflow(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.is_file(), f"missing workflow {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _postgres_jobs(workflow_name: str) -> list[tuple[str, dict]]:
    jobs = _workflow(workflow_name).get("jobs", {})
    found: list[tuple[str, dict]] = []
    for job_name, job in jobs.items():
        postgres = job.get("services", {}).get("postgres")
        if postgres is not None:
            found.append((job_name, job))
    assert found, f"{workflow_name}: expected at least one postgres service job"
    return found


def _job_runtime_text(job: dict) -> str:
    parts: list[str] = []
    env = job.get("env", {})
    if env:
        parts.extend(f"{key}={value}" for key, value in env.items())
    for step in job.get("steps", []):
        step_env = step.get("env", {})
        if step_env:
            parts.extend(f"{key}={value}" for key, value in step_env.items())
        run = step.get("run")
        if run:
            parts.append(run)
    return "\n".join(parts)


def test_postgres_services_use_random_host_ports() -> None:
    """Postgres services must not bind a fixed host port."""
    for workflow_name in POSTGRES_WORKFLOWS:
        for job_name, job in _postgres_jobs(workflow_name):
            ports = job["services"]["postgres"].get("ports")
            assert ports == [5432], (
                f"{workflow_name}:{job_name}: use `ports: - 5432` so GitHub assigns"
                " a free host port instead of racing on `5432:5432`."
            )


def test_postgres_service_options_do_not_override_server_port() -> None:
    """The container still listens on 5432; only the host mapping is dynamic."""
    for workflow_name in POSTGRES_WORKFLOWS:
        for job_name, job in _postgres_jobs(workflow_name):
            options = job["services"]["postgres"].get("options", "")
            assert "--port" not in options, (
                f"{workflow_name}:{job_name}: service `options:` must not try to"
                " change the Postgres server port; use a random host mapping instead."
            )
            assert "pg_isready -p 543" not in options, (
                f"{workflow_name}:{job_name}: health checks should probe the default container port 5432, not a custom host port."
            )


def test_postgres_test_steps_use_assigned_host_port() -> None:
    """Every Postgres test job must connect through the assigned host port."""
    for workflow_name in POSTGRES_WORKFLOWS:
        for job_name, job in _postgres_jobs(workflow_name):
            runtime_text = _job_runtime_text(job)
            assert RANDOM_PORT_CONTEXT in runtime_text, (
                f"{workflow_name}:{job_name}: test step must build DATAFORGE_DATABASE_URL with {RANDOM_PORT_CONTEXT}."
            )
            assert "localhost:5432/testdb" not in runtime_text, (
                f"{workflow_name}:{job_name}: fixed localhost:5432 DSNs recreate the port-collision bug."
            )
