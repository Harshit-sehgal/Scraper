# compileall

- status: failed
- command: `/usr/bin/python3 -m compileall -q backend scripts architecture_validator.py`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T23:17:55.461802+00:00
- end_time: 2026-06-16T23:17:55.533049+00:00
- duration_seconds: 0.07
- exit_code: 1
- timeout_seconds: 60
- required: true
- redaction_applied: false

## stdout

```text
*** Error compiling 'backend/app/transactional_priority_queue.py'...
  File "backend/app/transactional_priority_queue.py", line 326
    _queue: Any =
                 ^
SyntaxError: invalid syntax


```

## stderr

```text

```
