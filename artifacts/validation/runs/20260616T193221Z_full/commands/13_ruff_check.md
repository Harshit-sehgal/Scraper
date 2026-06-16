# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:36:47.092250+00:00
- end_time: 2026-06-16T19:36:47.123460+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:528:120
    |
526 |                 memory.record_success(url, provided_selectors)
527 |                 _record_field_provenance(
528 |                     provenance_builder, schema_fields, provided_results, ExtractionMethod.DISCOVERY, provided_selectors
    |                                                                                                                        ^
529 |                 )
530 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:609:114
    |
607 |                 memory.record_success(url, remembered_selectors)
608 |                 _record_field_provenance(
609 |                     provenance_builder, schema_fields, raw_results, ExtractionMethod.MEMORY, remembered_selectors
    |                                                                                                                  ^
610 |                 )
611 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/extraction_orchestrator.py:705:117
    |
703 |                 memory.record_success(url, discovered_selectors)
704 |                 _record_field_provenance(
705 |                     provenance_builder, schema_fields, raw_results, ExtractionMethod.DISCOVERY, discovered_selectors
    |                                                                                                                     ^
706 |                 )
707 |                 return _arbitrate_and_return(
    |
help: Add trailing comma

I001 [*] Import block is un-sorted or un-formatted
  --> backend/tests/test_migrate_workflows_to_json_store.py:15:1
   |
13 |   """
14 |
15 | / from __future__ import annotations
16 | |
17 | | import json
18 | | import sqlite3
19 | | import os
20 | | import sys
21 | | from pathlib import Path
22 | |
23 | | import pytest
   | |_____________^
24 |
25 |   # Pin the same env the production router expects (avoids dotenv load).
   |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
  --> backend/tests/test_migrate_workflows_to_json_store.py:39:1
   |
37 |   sys.path.insert(0, str(_REPO_ROOT))
38 |
39 | / from scripts.migrate_workflows_to_json_store import (  # noqa: E402
40 | |     _WORKFLOW_COLUMNS,
41 | |     migrate_workflows,
42 | | )
   | |_^
   |
help: Organize imports

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> backend/tests/test_migrate_workflows_to_json_store.py:39:56
   |
37 | sys.path.insert(0, str(_REPO_ROOT))
38 |
39 | from scripts.migrate_workflows_to_json_store import (  # noqa: E402
   |                                                        ^^^^^^^^^^^^
40 |     _WORKFLOW_COLUMNS,
41 |     migrate_workflows,
   |
help: Remove unused `noqa` directive

S608 Possible SQL injection vector through string-based query construction
   --> backend/tests/test_migrate_workflows_to_json_store.py:125:13
    |
123 |     with sqlite3.connect(str(db_path)) as conn:
124 |         conn.execute(
125 |             f"INSERT INTO workflows ({', '.join(_WORKFLOW_COLUMNS)}) VALUES ({placeholders})",
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
126 |             values,
127 |         )
    |

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:151:18
    |
149 |                     {"id": "step-1", "kind": "navigate", "url": "https://example.com/list"},
150 |                     {"id": "step-2", "kind": "extract", "selector": "div.hotel"},
151 |                 ]
    |                  ^
152 |             ),
153 |             extraction_schema=json.dumps(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:154:89
    |
152 |             ),
153 |             extraction_schema=json.dumps(
154 |                 [{"name": "title", "kind": "text"}, {"name": "price", "kind": "number"}]
    |                                                                                         ^
155 |             ),
156 |             pagination_config=json.dumps({"strategy": "click_next", "max_pages": 10}),
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:193:16
    |
191 |                 name TEXT NOT NULL DEFAULT ''
192 |             )
193 |             """
    |                ^
194 |         )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:215:46
    |
214 | def test_migrate_writes_correctly_deserialized_records(
215 |     legacy_workflows_db: Path, tmp_path: Path
    |                                              ^
216 | ) -> None:
217 |     """JSON columns are deserialized; auth_profile_id is coerced to None when NULL."""
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:316:16
    |
314 |                 total_runs INTEGER DEFAULT 0
315 |             )
316 |             """
    |                ^
317 |         )
318 |         columns = [
    |
help: Add trailing comma

S608 Possible SQL injection vector through string-based query construction
   --> backend/tests/test_migrate_workflows_to_json_store.py:352:13
    |
350 |         valid_values[18] = "2026-01-01T00:00:00+00:00"
351 |         conn.execute(
352 |             f"INSERT INTO workflows ({', '.join(columns)}) VALUES ({placeholders})",
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
353 |             valid_values,
354 |         )
    |

S608 Possible SQL injection vector through string-based query construction
   --> backend/tests/test_migrate_workflows_to_json_store.py:359:13
    |
357 |         empty_values[16] = 1
358 |         conn.execute(
359 |             f"INSERT INTO workflows ({', '.join(columns)}) VALUES ({placeholders})",
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
360 |             empty_values,
361 |         )
    |

COM812 [*] Trailing comma missing
   --> backend/tests/test_migrate_workflows_to_json_store.py:404:16
    |
402 |                 total_runs INTEGER DEFAULT 0
403 |             )
404 |             """
    |                ^
405 |         )
406 |         conn.execute(
    |
help: Add trailing comma

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> scripts/migrate_workflows_to_json_store.py:67:54
   |
65 | os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")
66 |
67 | from app.utils.json_file_store import JSONFileStore  # noqa: E402
   |                                                      ^^^^^^^^^^^^
68 |
69 | logger = logging.getLogger("migrate_workflows")
   |
help: Remove unused `noqa` directive

RUF100 [*] Unused `noqa` directive (non-enabled: `BLE001`)
   --> scripts/migrate_workflows_to_json_store.py:113:31
    |
111 |         if settings.STATE_FILE_PATH_DYNAMIC:
112 |             settings_path = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
113 |     except Exception as exc:  # noqa: BLE001  # private-shaped fallback
    |                               ^^^^^^^^^^^^^^
114 |         logger.debug("could not read settings.STATE_FILE_PATH_DYNAMIC: %s", exc)
115 |     if settings_path is not None:
    |
help: Remove unused `noqa` directive

SIM118 Use `key in dict` instead of `key in dict.keys()`
   --> scripts/migrate_workflows_to_json_store.py:142:27
    |
140 |     """
141 |     record: dict[str, Any] = {
142 |         col: row[col] for col in row.keys() if col in _WORKFLOW_COLUMNS
    |                           ^^^^^^^^^^^^^^^^^
143 |     }
144 |     workflow_id = str(record.get("id") or "").strip()
    |
help: Remove `.keys()`

TRY400 Use `logging.exception` instead of `logging.error`
   --> scripts/migrate_workflows_to_json_store.py:289:9
    |
287 |         )
288 |     except FileNotFoundError as exc:
289 |         logger.error("%s", exc)
    |         ^^^^^^^^^^^^^^^^^^^^^^^
290 |         return 2
291 |     except sqlite3.OperationalError as exc:
    |
help: Replace with `exception`

TRY401 Redundant exception object included in `logging.exception` call
   --> scripts/migrate_workflows_to_json_store.py:294:53
    |
292 |         # Schema mismatch (e.g. un-migrated v8 DB) — log with traceback so
293 |         # operators see which column is missing.
294 |         logger.exception("SQLite schema error: %s", exc)
    |                                                     ^^^
295 |         return 3
296 |     except sqlite3.DatabaseError as exc:
    |

TRY401 Redundant exception object included in `logging.exception` call
   --> scripts/migrate_workflows_to_json_store.py:297:46
    |
295 |         return 3
296 |     except sqlite3.DatabaseError as exc:
297 |         logger.exception("SQLite error: %s", exc)
    |                                              ^^^
298 |         return 3
    |

Found 21 errors.
[*] 14 fixable with the `--fix` option (2 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
