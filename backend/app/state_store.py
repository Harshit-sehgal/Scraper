"""Simple JSON persistence for job and recycle-bin state."""

from __future__ import annotations

import datetime
import json
import logging
import os
from pathlib import Path
from threading import Lock

from app.models import Job, JobStatus

_STATE_LOCK = Lock()
_DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "jobs_state.json"


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


def get_state_file_path() -> Path:
    configured = os.getenv("DATAFORGE_STATE_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_STATE_FILE


def load_state() -> tuple[dict[str, Job], dict[str, Job]]:
    path = get_state_file_path()
    if not path.exists():
        return {}, {}

    with _STATE_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.exception(e)
            print(f"[State] Failed to read state file {path}: {e}")
            return {}, {}

    jobs_store: dict[str, Job] = {}
    recycle_bin_store: dict[str, Job] = {}

    for raw in payload.get("jobs", []):
        try:
            job = Job.model_validate(raw)
            jobs_store[job.id] = job
        except Exception as e:
            logging.exception(e)
            print(f"[State] Skipping invalid job entry: {e}")

    for raw in payload.get("recycle_bin", []):
        try:
            job = Job.model_validate(raw)
            recycle_bin_store[job.id] = job
        except Exception as e:
            logging.exception(e)
            print(f"[State] Skipping invalid recycle-bin entry: {e}")

    # Jobs that were in-progress during shutdown are marked failed on recovery.
    for job in jobs_store.values():
        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
            job.status = JobStatus.FAILED
            job.error = "Recovered after restart while still in progress."
            job.completed_at = _now_iso()
            job.cancel_requested = False

    return jobs_store, recycle_bin_store


def save_state(jobs_store: dict[str, Job], recycle_bin_store: dict[str, Job]) -> None:
    path = get_state_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "saved_at": _now_iso(),
        "jobs": [job.model_dump() for job in jobs_store.values()],
        "recycle_bin": [job.model_dump() for job in recycle_bin_store.values()],
    }

    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with _STATE_LOCK:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(path)
    except Exception as e:
        logging.exception(e)
        print(f"[State] Failed to persist state to {path}: {e}")
