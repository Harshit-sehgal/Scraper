# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T03:09:29.603127+00:00
- end_time: 2026-06-13T03:09:29.638041+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
S501 Probable use of `httpx` call with `verify=False` disabling SSL certificate checks
   --> backend/app/routers/auth_profiles.py:251:13
    |
249 |             follow_redirects=True,
250 |             timeout=15.0,
251 |             verify=False,  # nosec: target domains may use self-signed certs
    |             ^^^^^^^^^^^^
252 |         ) as client:
253 |             response = client.get(
    |

Found 1 error.

```

## stderr

```text

```
