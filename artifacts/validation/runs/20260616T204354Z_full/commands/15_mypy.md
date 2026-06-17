# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T20:48:28.031880+00:00
- end_time: 2026-06-16T20:48:28.782191+00:00
- duration_seconds: 0.75
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/saas/identity_store.py:200: error: Name "SelectedContext" is not defined  [name-defined]
backend/app/saas/identity_store.py:203: error: Name "SelectedContext" is not defined  [name-defined]
backend/app/saas/identity_store.py:724: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_scraper_hostile_fixture_e2e.py:101: error: The return type of a generator function should be "Generator" or one of its supertypes  [misc]
backend/tests/test_workflow_pagination_e2e.py:168: error: Incompatible types in assignment (expression has type "def _per_page_stub(page_obj: _MockPage, workflow: Any = ...) -> Coroutine[Any, Any, list[dict[str, Any]]]", variable has type "def _extract_records_from_page(page: Any, workflow: Workflow) -> Coroutine[Any, Any, list[dict[str, Any]]]")  [assignment]
backend/tests/test_workflow_pagination_e2e.py:215: error: Incompatible types in assignment (expression has type "def _per_page_stub(page_obj: _MockPage, workflow: Any = ...) -> Coroutine[Any, Any, list[dict[str, Any]]]", variable has type "def _extract_records_from_page(page: Any, workflow: Workflow) -> Coroutine[Any, Any, list[dict[str, Any]]]")  [assignment]
backend/tests/test_saas_router.py:16: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_saas_identity.py:47: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_p1_compliance_aup.py:39: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_p0_auth_tenant.py:61: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_p0_auth_tenant.py:245: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
backend/tests/test_p0_auth_tenant.py:559: error: Cannot instantiate abstract class "SQLiteIdentityStore" with abstract attributes "clear", "get_selected" and "set_selected"  [abstract]
Found 12 errors in 7 files (checked 553 source files)

```

## stderr

```text

```
