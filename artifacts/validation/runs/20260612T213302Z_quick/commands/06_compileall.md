# compileall

- status: failed
- command: `/usr/bin/python3 -m compileall -q backend scripts architecture_validator.py`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T21:33:02.548866+00:00
- end_time: 2026-06-12T21:33:02.639754+00:00
- duration_seconds: 0.09
- exit_code: 1
- timeout_seconds: 60
- required: true
- redaction_applied: false

## stdout

```text
*** Error compiling 'backend/app/saas/router.py'...
  File "backend/app/saas/router.py", line 726
    raise HTTPException(status_code=404, detail="
                                                ^
SyntaxError: unterminated string literal (detected at line 726)


```

## stderr

```text

```
