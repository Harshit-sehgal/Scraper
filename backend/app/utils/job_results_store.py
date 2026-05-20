"""
Job Results Store — Utility to compress and stream large record datasets to/from disk.
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


def save_job_results_to_disk(job_id: str, results: list[dict]) -> str:
    """
    Compress and write the list of record dictionaries to disk in JSONLines format.
    
    Returns the absolute string path to the saved file.
    """
    path = get_job_results_path(job_id)
    logger.info("Offloading %d records to disk for job %s at %s", len(results), job_id, path)
    
    # Write to a temporary file first and then atomically rename it to prevent corruption
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
            except Exception:
                pass
        raise e
        
    return str(path)


def load_job_results_from_disk(job_id: str) -> list[dict]:
    """
    Decompress and load the list of record dictionaries from disk for a given job ID.
    
    Returns an empty list if the file does not exist.
    """
    path = get_job_results_path(job_id)
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


def delete_job_results_from_disk(job_id: str) -> bool:
    """
    Delete the compressed results file from disk for a given job ID.
    
    Returns True if the file was deleted, False otherwise.
    """
    path = get_job_results_path(job_id)
    if path.exists():
        try:
            path.unlink()
            logger.info("Successfully deleted results file from disk for job %s", job_id)
            return True
        except Exception as e:
            logger.error("Failed to delete results file from disk for job %s: %s", job_id, e)
    return False
