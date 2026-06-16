# pyflakes

- status: failed
- command: `/usr/bin/python3 -m pyflakes backend/app backend/tests scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T22:14:40.850396+00:00
- end_time: 2026-06-12T22:14:43.070631+00:00
- duration_seconds: 2.22
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/plan_enforcer.py:17:1: 'functools.lru_cache' imported but unused
backend/app/plan_enforcer.py:22:1: 'app.utils.rbac.AuthContext' imported but unused

```

## stderr

```text

```
