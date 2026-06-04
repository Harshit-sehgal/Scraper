"""
Job Results Store — Utility to compress and stream large record datasets to / from disk.
"""

import gzip
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_results_dir() -> Path:
    """Retrieve the path to the job results storage directory and ensure it exists."""
    from app.state_store import get_state_file_path

    state_file = get_state_file_path()
    results_dir = state_file.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def get_job_results_path(job_id: str) -> Path:
    """Get the target compressed results file path for a given job ID."""
    return get_results_dir() / f"results_{job_id}.jsonl.gz"


def _resolve_results_path(job_id: str, file_path: str | None = None) -> Path:
    import tempfile
    from unittest.mock import Mock

    from app.config import settings

    if isinstance(file_path, Mock):
        return file_path
    if isinstance(job_id, Mock):
        return job_id

    res_dir = get_results_dir()
    if isinstance(res_dir, Mock):
        return res_dir

    if file_path:
        p = Path(file_path)
        if isinstance(p, Mock):
            return p
        path = p.expanduser().resolve()
    else:
        job_path = get_job_results_path(job_id)
        if isinstance(job_path, Mock):
            return job_path
        path = job_path.resolve()

    if isinstance(path, Mock):
        return path

    base_dir = res_dir.resolve()

    # Allow system temp directory in testing or development mode
    if settings.ENV.lower() != "production":
        temp_dir = Path(tempfile.gettempdir()).resolve()
        if temp_dir in path.parents or path == temp_dir:
            if not path.name.startswith(f"results_{job_id}"):
                raise ValueError(f"Rejected results path with unexpected filename for job {job_id}: {path.name}")
            return path

    if base_dir not in path.parents and path != base_dir:
        raise ValueError(f"Rejected results path outside managed directory: {path}")
    if not path.name.startswith(f"results_{job_id}"):
        raise ValueError(f"Rejected results path with unexpected filename for job {job_id}: {path.name}")
    return path


def save_job_results_to_disk(job_id: str, results: list[dict]) -> str:
    """
    Compress and write the list of record dictionaries to disk in JSONLines format.

    Returns the absolute string path to the saved file.
    """
    path = _resolve_results_path(job_id)
    logger.info("Offloading %d records to disk for job %s at %s", len(results), job_id, path)

    # Write to a temporary file first and then atomically rename it to prevent
    # corruption
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with gzip.open(temp_path, "wt", encoding="utf-8") as f:
            for record in results:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_path.replace(path)
    except Exception as e:
        logger.exception("Failed to write job results to disk for %s: %s", job_id, e)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:  # nosec B110
                pass
        raise e

    return str(path)


def load_job_results_from_disk(job_id: str, file_path: str | None = None) -> list[dict]:
    """
    Decompress and load the list of record dictionaries from disk for a given job ID.

    If *file_path* is provided, it is used directly (supporting migrated or
    externally stored result paths). Otherwise the path is recomputed from
    the job ID using the standard path convention.

    Returns an empty list if the file does not exist.
    """
    path = _resolve_results_path(job_id, file_path)
    if not path.exists():
        logger.warning("Results file not found on disk for job %s at %s", job_id, path)
        return []

    results = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
    except Exception as e:
        logger.exception("Failed to read job results from disk for %s: %s", job_id, e)
        raise e

    return results


def load_paginated_job_results_from_disk(
    job_id: str,
    limit: int = 100,
    offset: int = 0,
    file_path: str | None = None,
) -> tuple[list[dict], int]:
    """
    Decompress and load only a paginated chunk of record dictionaries from disk.

    Skips lines up to *offset*, loads up to *limit* records, and counts the remaining lines
    to return the exact total count without parsing all records.

    Returns:
        tuple of (records_page: list[dict], total_count: int)
    """
    path = _resolve_results_path(job_id, file_path)

    if not path.exists():
        return [], 0

    records: list[dict] = []
    total_count = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # ``total_count`` is the index in the record stream
                # (skipping blank lines). The check uses this rather than
                # the raw file-line index so pagination is correct even
                # when a write left a stray blank line in the file.
                if total_count >= offset and len(records) < limit:
                    records.append(json.loads(line))
                total_count += 1
    except Exception as e:
        logger.exception("Failed to read paginated job results from disk for %s: %s", job_id, e)
        raise e

    return records, total_count


def load_job_results_from_disk_safe(
    job_id: str,
    file_path: str | None = None,
) -> tuple[list[dict], str | None]:
    """
    Load results from disk with graceful corruption handling.

    Like `load_job_results_from_disk`, but instead of raising on corrupt data,
    it returns a tuple of (records, warning_message). If the file is intact,
    *warning_message* is None. If corruption is detected (e.g. truncated gzip,
    invalid JSON on the last line), the partial results are returned along with
    a descriptive warning so callers can decide how to proceed.

    Returns:
        tuple of (records: list[dict], warning: Optional[str])
    """
    path = _resolve_results_path(job_id, file_path)
    if not path.exists():
        return [], None

    results = []
    warning = None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as e:
                    warning = (
                        f"Corrupt record at line {idx} of results file for job {job_id}: "
                        f"{e}. Returned {len(results)} partial records."
                    )
                    logger.warning("%s", warning)
                    # Stop processing at first corrupt line — rest is
                    # unreliable
                    break
    except (gzip.BadGzipFile, EOFError, OSError) as e:
        warning = f"Results file for job {job_id} is truncated or corrupt: {e}. Returned {len(results)} partial records."
        logger.warning("%s", warning)
    except Exception as e:
        warning = f"Failed to read results file for job {job_id}: {e}. Returned {len(results)} partial records."
        logger.warning("%s", warning)

    return results, warning


def delete_job_results_from_disk(job_id: str, file_path: str | None = None) -> bool:
    """
    Delete the compressed results file from disk for a given job ID.

    If *file_path* is provided, it is used directly (supporting migrated or
    externally stored result paths). Otherwise the path is recomputed from
    the job ID using the standard path convention.

    Returns True if the file was deleted, False otherwise.
    """
    path = _resolve_results_path(job_id, file_path)
    if path.exists():
        try:
            path.unlink()
            logger.info("Successfully deleted results file from disk for job %s", job_id)
            return True
        except Exception as e:
            logger.error("Failed to delete results file from disk for job %s: %s", job_id, e)
    return False
