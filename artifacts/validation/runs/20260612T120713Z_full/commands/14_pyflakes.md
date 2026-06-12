# pyflakes

- status: failed
- command: `/usr/bin/python3 -m pyflakes backend/app backend/tests scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T12:10:53.802330+00:00
- end_time: 2026-06-12T12:10:55.951037+00:00
- duration_seconds: 2.15
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/models.py:566:1: redefinition of unused 'AuthProfile' from line 469
backend/app/url_analyzer.py:478:5: local variable 'parsed' is assigned to but never used
backend/app/routers/auth_profiles.py:18:1: 'app.models.AuthProfileStatus' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.User' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.UserStatus' imported but unused
backend/tests/test_scheduled_monitoring.py:3:1: 'pytest' imported but unused
backend/tests/test_auth_profiles.py:3:1: 'pytest' imported but unused

```

## stderr

```text

```
