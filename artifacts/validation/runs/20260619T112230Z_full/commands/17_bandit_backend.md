# bandit_backend

- status: failed
- command: `/usr/bin/python3 -m bandit -r backend -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-19T11:27:29.102827+00:00
- end_time: 2026-06-19T11:27:32.873286+00:00
- duration_seconds: 3.77
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: true

## stdout

```text
Run started:2026-06-19 11:27:32.826394+00:00

Test results:
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: [REDACTED]
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b105_hardcoded_password_string.html
   Location: backend/app/billing/service.py:40:28
39	_PAYPAL_CLIENT_ID_ENV = "PAYPAL_CLIENT_ID"
40	_PAYPAL_CLIENT_SECRET_ENV = [REDACTED]
41	_PAYPAL_API_URL_ENV = "PAYPAL_API_URL"

--------------------------------------------------

Code scanned:
	Total lines of code: 63286
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 40

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 1
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 1
		High: 0
Files skipped (0):

```

## stderr

```text
[main]	INFO	Found project level .bandit file: backend/.bandit
[main]	INFO	Using command line arg for selected targets
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/admin_denylist.py:176
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/admin_denylist.py:199
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/admin_denylist.py:202
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/postgres_repository.py:126
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:864
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:864
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:886
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:886
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:912
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:912
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1083
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1083
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1101
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1101
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1123
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1123
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1134
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/postgres_repository_base.py:1134
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/psycopg3_repository.py:152
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/scraper.py:266
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/storage_interface.py:460
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/storage_interface.py:543
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:110
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:116
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:168
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:174
[manager]	WARNING	Test in comment: string is not a test name or id, ignoring
[manager]	WARNING	Test in comment: equality is not a test name or id, ignoring
[manager]	WARNING	Test in comment: against is not a test name or id, ignoring
[manager]	WARNING	Test in comment: empty is not a test name or id, ignoring
[manager]	WARNING	Test in comment: string is not a test name or id, ignoring
[manager]	WARNING	Test in comment: no is not a test name or id, ignoring
[manager]	WARNING	Test in comment: credential is not a test name or id, ignoring
[manager]	WARNING	Test in comment: present is not a test name or id, ignoring
[manager]	WARNING	Test in comment: initialized is not a test name or id, ignoring
[manager]	WARNING	Test in comment: empty is not a test name or id, ignoring
[manager]	WARNING	Test in comment: populated is not a test name or id, ignoring
[manager]	WARNING	Test in comment: below is not a test name or id, ignoring
[manager]	WARNING	Test in comment: only is not a test name or id, ignoring
[manager]	WARNING	Test in comment: on is not a test name or id, ignoring
[manager]	WARNING	Test in comment: valid is not a test name or id, ignoring
[manager]	WARNING	Test in comment: Bearer is not a test name or id, ignoring
[manager]	WARNING	Test in comment: prefix is not a test name or id, ignoring
[manager]	WARNING	Test in comment: this is not a test name or id, ignoring
[manager]	WARNING	Test in comment: rejects is not a test name or id, ignoring
[manager]	WARNING	Test in comment: bind is not a test name or id, ignoring
[manager]	WARNING	Test in comment: all is not a test name or id, ignoring
[manager]	WARNING	Test in comment: and is not a test name or id, ignoring
[manager]	WARNING	Test in comment: loopback is not a test name or id, ignoring
[manager]	WARNING	Test in comment: targets is not a test name or id, ignoring
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/forge_kernel/security/url_safety.py:53
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/forge_kernel/security/url_safety.py:53
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/forge_kernel/security/url_safety.py:53
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/forge_kernel/security/url_safety.py:53
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/forge_kernel/security/url_safety.py:53

```
