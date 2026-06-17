# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:47:23.490571+00:00
- end_time: 2026-06-16T19:47:23.529368+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
F821 Undefined name `arbitrate_sources`
   --> backend/app/extraction_orchestrator.py:292:50
    |
291 |     # Arbitrate sources
292 |     winning_records, winning_source, field_map = arbitrate_sources(
    |                                                  ^^^^^^^^^^^^^^^^^
293 |         dom_records,
294 |         dom_score,
    |

F401 [*] `app.network_payload_extractor.arbitrate_sources` imported but unused
   --> backend/app/extraction_orchestrator.py:438:9
    |
436 |     # Extract network results
437 |     from app.network_payload_extractor import (
438 |         arbitrate_sources,
    |         ^^^^^^^^^^^^^^^^^
439 |         extract_from_network_payloads,
440 |     )
    |
help: Remove unused import: `app.network_payload_extractor.arbitrate_sources`

F841 Local variable `network_diagnostics` is assigned to but never used
   --> backend/app/extraction_orchestrator.py:447:5
    |
445 |     network_score = network_result.score if network_result else 0.0
446 |
447 |     network_diagnostics = [
    |     ^^^^^^^^^^^^^^^^^^^
448 |         f"session-bound detection result: {is_session}",
449 |         f"captured payload count: {captured_count}",
    |
help: Remove assignment to unused variable `network_diagnostics`

Found 3 errors.
[*] 1 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
