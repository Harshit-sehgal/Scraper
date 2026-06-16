# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:15:15.872285+00:00
- end_time: 2026-06-16T19:15:15.913924+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:530:120
    |
528 |                 memory.record_success(url, provided_selectors)
529 |                 _record_field_provenance(
530 |                     provenance_builder, schema_fields, provided_results, ExtractionMethod.DISCOVERY, provided_selectors
    |                                                                                                                        ^
531 |                 )
532 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:611:114
    |
609 |                 memory.record_success(url, remembered_selectors)
610 |                 _record_field_provenance(
611 |                     provenance_builder, schema_fields, raw_results, ExtractionMethod.MEMORY, remembered_selectors
    |                                                                                                                  ^
612 |                 )
613 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:707:117
    |
705 |                 memory.record_success(url, discovered_selectors)
706 |                 _record_field_provenance(
707 |                     provenance_builder, schema_fields, raw_results, ExtractionMethod.DISCOVERY, discovered_selectors
    |                                                                                                                     ^
708 |                 )
709 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

Found 3 errors.
[*] 3 fixable with the `--fix` option.

```

## stderr

```text

```
