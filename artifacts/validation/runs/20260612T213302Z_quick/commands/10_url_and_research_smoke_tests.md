# url_and_research_smoke_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T21:33:03.951785+00:00
- end_time: 2026-06-12T21:33:05.172370+00:00
- duration_seconds: 1.22
- exit_code: 4
- timeout_seconds: 120
- required: true
- redaction_applied: false

## stdout

```text

```

## stderr

```text
ImportError while loading conftest '/home/harshit/Documents/Work/Money/scraper/backend/tests/conftest.py'.
backend/tests/conftest.py:251: in <module>
    import app.main
backend/app/main.py:52: in <module>
    from app.saas.router import router as saas_router
E     File "/home/harshit/Documents/Work/Money/scraper/backend/app/saas/router.py", line 726
E       raise HTTPException(status_code=404, detail="
E                                                   ^
E   SyntaxError: unterminated string literal (detected at line 726)

```
