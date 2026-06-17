# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T14:43:19.947722+00:00
- end_time: 2026-06-17T14:43:19.980249+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
F821 Undefined name `settings`
   --> backend/app/routers/auth_profiles.py:265:20
    |
263 |             follow_redirects=True,
264 |             timeout=15.0,
265 |             verify=settings.VERIFY_SSL if hasattr(settings, "VERIFY_SSL") else True,
    |                    ^^^^^^^^
266 |         ) as client:
267 |             response = await client.get(
    |

F821 Undefined name `settings`
   --> backend/app/routers/auth_profiles.py:265:51
    |
263 |             follow_redirects=True,
264 |             timeout=15.0,
265 |             verify=settings.VERIFY_SSL if hasattr(settings, "VERIFY_SSL") else True,
    |                                                   ^^^^^^^^
266 |         ) as client:
267 |             response = await client.get(
    |

EM101 Exception must not use a string literal, assign to variable first
  --> backend/app/routers/exports.py:65:30
   |
63 |     def _validate_format(cls, value: str) -> str:
64 |         if value not in ("csv", "json", "xlsx"):
65 |             raise ValueError("format must be one of: csv, json, xlsx")
   |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
66 |         return value
67 |     flatten: bool = Field(
   |
help: Assign to variable; remove string literal

Found 3 errors.
No fixes available (1 hidden fix can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
