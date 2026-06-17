# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T20:48:25.666428+00:00
- end_time: 2026-06-16T20:48:25.694694+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
F821 Undefined name `SelectedContext`
   --> backend/app/saas/identity_store.py:200:75
    |
199 |     @abstractmethod
200 |     def set_selected(self, user_id: str, org_id: str, project_id: str) -> SelectedContext: ...
    |                                                                           ^^^^^^^^^^^^^^^
201 |
202 |     @abstractmethod
    |

F821 Undefined name `SelectedContext`
   --> backend/app/saas/identity_store.py:203:45
    |
202 |     @abstractmethod
203 |     def get_selected(self, user_id: str) -> SelectedContext | None: ...
    |                                             ^^^^^^^^^^^^^^^
204 |
205 |     @abstractmethod
    |

Found 2 errors.

```

## stderr

```text

```
