# openapi_spec

- status: passed
- command: `/usr/bin/python3 scripts/generate_openapi.py --no-docs-copy`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T00:59:39.863215+00:00
- end_time: 2026-06-17T00:59:40.908823+00:00
- duration_seconds: 1.05
- exit_code: 0
- timeout_seconds: 120
- required: true
- redaction_applied: false
- note: Generates artifacts/audit/openapi.json from the live FastAPI app.

## stdout

```text
Wrote /home/harshit/Documents/Work/Money/scraper/artifacts/audit/openapi.json
  path_count=84  operation_count=102
  GET=52
  POST=34
  PUT=2
  PATCH=1
  DELETE=13

```

## stderr

```text

```
