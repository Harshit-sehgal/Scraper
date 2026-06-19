# bandit_backend

- status: passed
- command: `/usr/bin/python3 -m bandit -r backend -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-19T09:11:07.111337+00:00
- end_time: 2026-06-19T09:11:10.762533+00:00
- duration_seconds: 3.65
- exit_code: 0
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text

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
