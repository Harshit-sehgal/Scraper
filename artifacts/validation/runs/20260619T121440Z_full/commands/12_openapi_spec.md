# openapi_spec

- status: passed
- command: `/usr/bin/python3 scripts/generate_openapi.py --no-docs-copy`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-19T12:14:58.611122+00:00
- end_time: 2026-06-19T12:14:59.649211+00:00
- duration_seconds: 1.04
- exit_code: 0
- timeout_seconds: 120
- required: true
- redaction_applied: false
- note: Generates artifacts/audit/openapi.json from the live FastAPI app.

## stdout

```text
Wrote /home/harshit/Documents/Work/Money/scraper/artifacts/audit/openapi.json
  path_count=85  operation_count=103
  GET=52
  POST=35
  PUT=2
  PATCH=1
  DELETE=13

```

## stderr

```text

```
