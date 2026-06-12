# pyflakes

- status: failed
- command: `/usr/bin/python3 -m pyflakes backend/app backend/tests scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T18:48:13.733809+00:00
- end_time: 2026-06-12T18:48:15.893066+00:00
- duration_seconds: 2.16
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/models.py:583:1: redefinition of unused 'AuthProfile' from line 486
backend/app/url_analyzer.py:650:5: local variable 'parsed' is assigned to but never used
backend/app/routers/auth_profiles.py:18:1: 'app.models.AuthProfileStatus' imported but unused
backend/app/routers/workflow.py:20:1: 'app.models.WorkflowStep' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.User' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.UserStatus' imported but unused
backend/tests/test_scheduled_monitoring.py:3:1: 'pytest' imported but unused
backend/tests/test_auth_profiles.py:3:1: 'pytest' imported but unused

```

## stderr

```text

```
