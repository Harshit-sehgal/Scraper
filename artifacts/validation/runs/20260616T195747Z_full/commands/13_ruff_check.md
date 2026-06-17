# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T20:02:17.502275+00:00
- end_time: 2026-06-16T20:02:17.533672+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:531:121
    |
529 |                 )
530 |                 return _arbitrate_and_return(
531 |                     ExtractionResult(provided_results, "discovery", selector_success=True, selectors=provided_selectors)
    |                                                                                                                         ^
532 |                 )
533 |             logger.info("[Orchestrator] Provided selectors LOW QUALITY (avg score: %.2f), falling through", avg_score)
    |
help: Add trailing comma

Found 1 error.
[*] 1 fixable with the `--fix` option.

```

## stderr

```text

```
