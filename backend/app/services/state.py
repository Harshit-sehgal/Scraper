from app.storage_interface import get_job_repository

_default_repo = get_job_repository()


def prune_history_stores(jobs_store: dict, recycle_bin_store: dict, max_job_history: int, max_recycle_bin_history: int):
    from app.models import JobStatus
    from app.utils.job_results_store import delete_job_results_from_disk
    
    if len(jobs_store) > max_job_history:
        active_ids = {
            jid
            for jid, job in jobs_store.items()
            if job.status not in {JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.EMPTY_RESULT, JobStatus.FAILED, JobStatus.CANCELED}
        }
        slots_for_terminal = max(0, max_job_history - len(active_ids))

        terminal_jobs = [
            (jid, job)
            for jid, job in jobs_store.items()
            if jid not in active_ids
        ]
        terminal_jobs.sort(key=lambda item: item[1].created_at, reverse=True)

        keep_ids = set(active_ids)
        keep_ids.update(jid for jid, _ in terminal_jobs[:slots_for_terminal])

        for jid in list(jobs_store.keys()):
            if jid not in keep_ids:
                del jobs_store[jid]
                delete_job_results_from_disk(jid)

    if len(recycle_bin_store) > max_recycle_bin_history:
        recycle_items = sorted(
            recycle_bin_store.items(),
            key=lambda item: item[1].created_at,
            reverse=True,
        )
        keep_ids = {jid for jid, _ in recycle_items[:max_recycle_bin_history]}
        for jid in list(recycle_bin_store.keys()):
            if jid not in keep_ids:
                del recycle_bin_store[jid]
                delete_job_results_from_disk(jid)

def persist_state(jobs_store: dict, recycle_bin_store: dict, max_job_history: int, max_recycle_bin_history: int):
    prune_history_stores(jobs_store, recycle_bin_store, max_job_history, max_recycle_bin_history)
    _default_repo.save_all(jobs=jobs_store, recycle_bin=recycle_bin_store)
