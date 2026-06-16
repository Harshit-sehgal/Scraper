# mypy

- status: failed
- command: `/usr/bin/python3 -m mypy backend`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T03:09:31.888880+00:00
- end_time: 2026-06-13T03:09:32.592332+00:00
- duration_seconds: 0.70
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
backend/app/billing/webhooks.py:78: error: Incompatible types in assignment (expression has type "Any | None", variable has type "str")  [assignment]
backend/app/billing/webhooks.py:97: error: Incompatible types in assignment (expression has type "Any | None", variable has type "str")  [assignment]
backend/app/billing/webhooks.py:106: error: Incompatible types in assignment (expression has type "Any | None", variable has type "str")  [assignment]
backend/app/billing/webhooks.py:120: error: Argument "subscription_id" to "set_customer_subscription" has incompatible type "Any | None"; expected "str"  [arg-type]
Found 4 errors in 1 file (checked 552 source files)

```

## stderr

```text

```
