# pyflakes

- status: failed
- command: `/usr/bin/python3 -m pyflakes backend/app backend/tests scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:47:23.530137+00:00
- end_time: 2026-06-16T19:47:25.991208+00:00
- duration_seconds: 2.46
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/extraction_orchestrator.py:292:50: undefined name 'arbitrate_sources'
backend/app/extraction_orchestrator.py:437:5: 'app.network_payload_extractor.arbitrate_sources' imported but unused
backend/app/extraction_orchestrator.py:447:5: local variable 'network_diagnostics' is assigned to but never used

```

## stderr

```text

```
