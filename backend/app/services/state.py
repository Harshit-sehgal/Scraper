from app.globals import _jobs_store_lock
from app.storage_interface import get_job_repository


def _compute_prunable_ids(
    store: dict,
    max_history: int,
) -> set:
    """Return the set of job IDs that should be pruned from *store*.

    Only terminal jobs (completed, degraded, empty, failed, canceled) are
    candidates for pruning. Active jobs are always kept.
    """
    from app.models import JobStatus

    if len(store) <= max_history:
        return set()

    terminal_statuses = {
        JobStatus.COMPLETED,
        JobStatus.DEGRADED,
        JobStatus.EMPTY_RESULT,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
    active_ids = {jid for jid, job in store.items() if job.status not in terminal_statuses}
    slots_for_terminal = max(0, max_history - len(active_ids))

    terminal_jobs = [(jid, job) for jid, job in store.items() if jid not in active_ids]
    terminal_jobs.sort(key=lambda item: item[1].created_at, reverse=True)

    keep_ids = set(active_ids)
    keep_ids.update(jid for jid, _ in terminal_jobs[:slots_for_terminal])

    return {jid for jid in store if jid not in keep_ids}


def persist_state(jobs_store: dict, recycle_bin_store: dict, max_job_history: int, max_recycle_bin_history: int) -> None:
    """Persist the in-memory stores to disk and database.

    Pruning happens on the *real* stores under the lock so that the
    in-memory state is actually updated.  File I/O (deleting result
    files) happens outside the lock to avoid blocking API reads.
    """
    from app.utils.job_results_store import delete_job_results_from_disk

    # Phase 1: Under the lock, compute prunable IDs and remove them
    # from the real stores.  Snapshot the stores for DB save.
    files_to_delete: list[tuple[str, str | None]] = []
    with _jobs_store_lock:
        prunable_jobs = _compute_prunable_ids(jobs_store, max_job_history)
        for jid in prunable_jobs:
            job = jobs_store.pop(jid, None)
            file_path = job.results_file_path if job else None
            files_to_delete.append((jid, file_path))

        prunable_recycle = _compute_prunable_ids(recycle_bin_store, max_recycle_bin_history)
        for jid in prunable_recycle:
            job = recycle_bin_store.pop(jid, None)
            file_path = job.results_file_path if job else None
            files_to_delete.append((jid, file_path))

        # Snapshot for DB save (after pruning)
        jobs_snapshot = dict(jobs_store)
        recycle_snapshot = dict(recycle_bin_store)

    # Phase 2: File I/O outside the lock
    for jid, file_path in files_to_delete:
        delete_job_results_from_disk(jid, file_path)

    # Phase 3: DB save outside the lock
    repo = get_job_repository()
    repo.save_all(jobs=jobs_snapshot, recycle_bin=recycle_snapshot)


def prune_history_stores(
    jobs_store: dict,
    recycle_bin_store: dict,
    max_job_history: int,
    max_recycle_bin_history: int,
) -> None:
    """Prune old terminal jobs from in-memory stores based on history limits.

    Removes the oldest terminal jobs from *jobs_store* and *recycle_bin_store*
    when they exceed the configured maximum history size. Active (non-terminal)
    jobs are always preserved.

    This is a convenience wrapper around :func:`_compute_prunable_ids` that
    directly mutates the provided dicts. File/deletion cleanup is the
    caller's responsibility.
    """
    prunable_jobs = _compute_prunable_ids(jobs_store, max_job_history)
    for jid in prunable_jobs:
        jobs_store.pop(jid, None)

    prunable_recycle = _compute_prunable_ids(recycle_bin_store, max_recycle_bin_history)
    for jid in prunable_recycle:
        recycle_bin_store.pop(jid, None)
