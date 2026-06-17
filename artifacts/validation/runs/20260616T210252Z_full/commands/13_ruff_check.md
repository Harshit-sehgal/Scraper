# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T21:07:21.395408+00:00
- end_time: 2026-06-16T21:07:21.426168+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
UP035 [*] Import from `collections.abc` instead: `Generator`
  --> backend/tests/test_scraper_hostile_fixture_e2e.py:35:1
   |
33 | import urllib.parse
34 | from pathlib import Path
35 | from typing import Any, Generator
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
36 |
37 | import pytest
   |
help: Import from `collections.abc`

UP037 [*] Remove quotes from type annotation
   --> backend/tests/test_workflow_pagination_e2e.py:164:55
    |
162 |     # forward clicks via scraper.run_load_more_extraction and feed each successful click
163 |     # through `_extract_records_from_page(page, workflow)`.)
164 |     async def _per_page_stub(page_obj: Any, workflow: "Workflow") -> list[dict[str, Any]]:
    |                                                       ^^^^^^^^^^
165 |         return await extract_stub(page_obj)
    |
help: Remove quotes

UP037 [*] Remove quotes from type annotation
   --> backend/tests/test_workflow_pagination_e2e.py:212:55
    |
210 |     workflow.id = workflow_dict["id"]
211 |
212 |     async def _per_page_stub(page_obj: Any, workflow: "Workflow") -> list[dict[str, Any]]:
    |                                                       ^^^^^^^^^^
213 |         return await extract_stub(page_obj)
    |
help: Remove quotes

Found 3 errors.
[*] 3 fixable with the `--fix` option.

```

## stderr

```text

```
