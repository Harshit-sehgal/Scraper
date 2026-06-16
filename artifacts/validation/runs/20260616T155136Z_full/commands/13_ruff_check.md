# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T15:56:08.843409+00:00
- end_time: 2026-06-16T15:56:08.873337+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
COM812 [*] Trailing comma missing
   --> backend/tests/test_pagination_async.py:328:14
    |
326 |                 [{"id": "k2", "value": "2"}, {"id": "k3", "value": "3"}],
327 |                 [{"id": "k3", "value": "3"}, {"id": "k4", "value": "4"}],
328 |             ]
    |              ^
329 |         )
    |
help: Add trailing comma

S110 `try`-`except`-`pass` detected, consider logging the exception
  --> backend/tests/test_postgres_integration.py:89:5
   |
87 |       try:
88 |           PostgresJobRepository().health_check()
89 | /     except Exception:
90 | |         pass  # _ensure() already ran on the line above.
   | |____________^
91 |       with _conn() as conn:
92 |           ensure_schema(conn)
   |

I001 [*] Import block is un-sorted or un-formatted
 --> backend/tests/test_production_hardening.py:1:1
  |
1 | / import socket
2 | | from pathlib import Path
3 | | from typing import Never
4 | |
5 | | import pytest
6 | |
7 | | import app.main as main_mod
8 | | from app.models import Job, JobStatus, ScrapeMode
9 | | from app.routers import jobs_write  # used by both B025 tests below  # noqa: PLC0415  — used by both B025 tests below
  | |__________________________________^
  |
help: Organize imports

RUF100 [*] Unused `noqa` directive (non-enabled: `PLC0415`)
 --> backend/tests/test_production_hardening.py:9:70
  |
7 | import app.main as main_mod
8 | from app.models import Job, JobStatus, ScrapeMode
9 | from app.routers import jobs_write  # used by both B025 tests below  # noqa: PLC0415  — used by both B025 tests below
  |                                                                      ^^^^^^^^^^^^^^^
  |
help: Remove unused `noqa` directive

COM812 [*] Trailing comma missing
   --> backend/tests/test_production_hardening.py:483:79
    |
481 |         "urls": ["https://example.com"],
482 |         "schema_fields": [
483 |             {"name": "company_name", "field_type": "string", "required": True}
    |                                                                               ^
484 |         ],
485 |     }
    |
help: Add trailing comma

PLW0108 Lambda may be unnecessary; consider inlining inner function
   --> backend/tests/test_production_hardening.py:499:9
    |
497 |         jobs_write,
498 |         "get_usage_ledger",
499 |         lambda: _QuotaFullLedger(),
    |         ^^^^^^^^^^^^^^^^^^^^^^^^^^
500 |     )
    |
help: Inline function call

COM812 [*] Trailing comma missing
   --> backend/tests/test_production_hardening.py:565:79
    |
563 |         "urls": ["https://example.com"],
564 |         "schema_fields": [
565 |             {"name": "company_name", "field_type": "string", "required": True}
    |                                                                               ^
566 |         ],
567 |     }
    |
help: Add trailing comma

Found 7 errors.
[*] 5 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
