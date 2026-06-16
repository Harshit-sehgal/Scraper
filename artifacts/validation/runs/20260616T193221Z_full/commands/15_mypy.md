# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T19:36:49.436991+00:00
- end_time: 2026-06-16T19:36:49.909874+00:00
- duration_seconds: 0.47
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/tests/test_migrate_workflows_to_json_store.py:348: error: No overload variant of "__setitem__" of "list" matches argument types "int", "int"  [call-overload]
backend/tests/test_migrate_workflows_to_json_store.py:348: note: Possible overload variants:
backend/tests/test_migrate_workflows_to_json_store.py:348: note:     def __setitem__(self, SupportsIndex, str | None, /) -> None
backend/tests/test_migrate_workflows_to_json_store.py:348: note:     def __setitem__(self, slice[SupportsIndex | None, SupportsIndex | None, SupportsIndex | None], Iterable[str | None], /) -> None
backend/tests/test_migrate_workflows_to_json_store.py:357: error: No overload variant of "__setitem__" of "list" matches argument types "int", "int"  [call-overload]
backend/tests/test_migrate_workflows_to_json_store.py:357: note: Possible overload variants:
backend/tests/test_migrate_workflows_to_json_store.py:357: note:     def __setitem__(self, SupportsIndex, str | None, /) -> None
backend/tests/test_migrate_workflows_to_json_store.py:357: note:     def __setitem__(self, slice[SupportsIndex | None, SupportsIndex | None, SupportsIndex | None], Iterable[str | None], /) -> None
Found 2 errors in 1 file (checked 547 source files)

```

## stderr

```text

```
