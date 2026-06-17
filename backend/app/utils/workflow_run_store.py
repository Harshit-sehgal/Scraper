"""File-backed WorkflowRun registry.

Each record is keyed by ``run_id`` (UUID4) and is appended by
``POST /api/workflows/{workflow_id}/run`` when the orchestrator
queues a workflow execution. A small status-update helper is
provided so the worker / job runner can mark a run as ``succeeded``
or ``failed`` without re-implementing the flock + atomic-rename
plumbing in every consumer.

Records persist to ``<repo>/data/workflow_runs.json`` by default
and can be repointed with ``DATAFORGE_WORKFLOW_RUNS_FILE`` for
test isolation or alternative deployments.

Schema (free-form dict, but the router enforces these keys):

* ``run_id`` (str)            — stable UUID4
* ``workflow_id`` (str)       — owning workflow
* ``job_id`` (str)            — job-store id used for status tracking
* ``user_id`` (str)           — RBAC principal that triggered the run
* ``org_id`` (str)            — tenant scope
* ``project_id`` (str)        — project scope
* ``status`` (str)            — ``queued`` | ``running`` | ``succeeded`` | ``failed`` | ``canceled``
* ``queued_at`` (str ISO 8601)
* ``started_at`` (str ISO 8601, optional)
* ``finished_at`` (str ISO 8601, optional)
* ``error`` (str, optional)
* ``records_count`` (int, optional) — populated by the worker on success
"""

from __future__ import annotations

import os
from pathlib import Path

from app.utils.json_file_store import JSONFileStore

DEFAULT_WORKFLOW_RUNS_FILENAME = "workflow_runs.json"
WORKFLOW_RUNS_ENV = "DATAFORGE_WORKFLOW_RUNS_FILE"


def default_workflow_runs_path() -> Path:
    """Resolve the on-disk path for the workflow-run store.

    Reads ``DATAFORGE_WORKFLOW_RUNS_FILE`` on every call so tests
    can override it after import and operators can repoint the
    store without restarting running workers.
    """
    env_value = os.environ.get(WORKFLOW_RUNS_ENV, "").strip()
    if env_value:
        return Path(env_value)
    return Path(__file__).resolve().parents[2] / "data" / DEFAULT_WORKFLOW_RUNS_FILENAME


class WorkflowRunStore(JSONFileStore):
    """File-backed WorkflowRun registry.

    Same persistence and concurrency contract as
    :class:`~app.utils.json_file_store.JSONFileStore`: read-through
    on every read, flock-serialised atomic write per mutation.
    Persists to ``<repo>/data/workflow_runs.json`` by default;
    override via ``DATAFORGE_WORKFLOW_RUNS_FILE``.
    """

    def _default_path(self) -> Path:
        return default_workflow_runs_path()
