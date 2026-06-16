# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T10:43:00.712315+00:00
- end_time: 2026-06-16T10:43:00.741225+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
B025 try-except block with duplicate exception `ValueError`
   --> backend/app/routers/jobs_write.py:297:44
    |
295 |                     logger.warning("Failed to hard-delete job %s after scheduled-job quota rejection", job.id)
296 |                 raise HTTPException(status_code=429, detail=str(e)) from e
297 |             except (RuntimeError, OSError, ValueError) as e:
    |                                            ^^^^^^^^^^
298 |                 if settings.ENV.lower() == "production":
299 |                     logger.exception(
    |

Found 1 error.

```

## stderr

```text

```
