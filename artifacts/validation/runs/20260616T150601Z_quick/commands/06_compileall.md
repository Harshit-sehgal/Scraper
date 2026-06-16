# compileall

- status: failed
- command: `/usr/bin/python3 -m compileall -q backend scripts architecture_validator.py`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T15:06:01.417031+00:00
- end_time: 2026-06-16T15:06:01.455329+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 60
- required: true
- redaction_applied: false

## stdout

```text
*** Error compiling 'backend/tests/test_pagination_async.py'...
  File "backend/tests/test_pagination_async.py", line 306
    assert result.stopped_reason == "timeout"    async def test_scroll_records_concatenate_across_pages(self):
                                                 ^^^^^
SyntaxError: invalid syntax


```

## stderr

```text

```
