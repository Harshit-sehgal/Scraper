# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:47:25.991624+00:00
- end_time: 2026-06-16T19:47:26.483668+00:00
- duration_seconds: 0.49
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/extraction_orchestrator.py:292: error: Name "arbitrate_sources" is not defined  [name-defined]
backend/app/extraction_orchestrator.py:498: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:540: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:624: error: Unexpected keyword argument "warnings" for "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:723: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:745: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:787: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:794: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:816: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
backend/app/extraction_orchestrator.py:820: error: Missing positional arguments "network_result", "network_diagnostics", "schema_fields", "provenance_builder" in call to "_arbitrate_and_return"  [call-arg]
Found 10 errors in 1 file (checked 547 source files)

```

## stderr

```text

```
