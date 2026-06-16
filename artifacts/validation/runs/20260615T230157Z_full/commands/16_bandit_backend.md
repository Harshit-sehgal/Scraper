# bandit_backend

- status: failed
- command: `/usr/bin/python3 -m bandit -r backend -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-15T23:06:27.473591+00:00
- end_time: 2026-06-15T23:06:31.193915+00:00
- duration_seconds: 3.72
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
Run started:2026-06-15 23:06:31.146576+00:00

Test results:
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_api.py:10:14
9	    for _ in range(60):
10	        res = requests.get(f"{BASE_URL}/api/jobs/{job_id}")
11	        data = res.json()

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_api.py:18:10
17	def test_manual() -> None:
18	    res = requests.post(
19	        f"{BASE_URL}/api/jobs",
20	        json={
21	            "name": "Manual Test",
22	            "mode": "manual",
23	            "intent": "Get interior designers",
24	            "topic": "interior designers",
25	            "urls": ["https://irishinterior.com/contact-us/"],
26	            "schema_fields": [
27	                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
28	                {"name": "email", "field_type": "email", "description": "email address", "required": False},
29	            ],
30	            "source_policy": "all_sources",
31	        },
32	    )
33	    job_id = res.json()["job_id"]

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_api.py:38:10
37	def test_auto() -> None:
38	    res = requests.post(
39	        f"{BASE_URL}/api/jobs",
40	        json={
41	            "name": "Auto Test",
42	            "mode": "auto",
43	            "intent": "Get interior designers in Chennai",
44	            "topic": "interior designers in chennai",
45	            "location": "chennai",
46	            "schema_fields": [
47	                {"name": "company_name", "field_type": "string", "description": "name of company", "required": True},
48	                {"name": "email", "field_type": "email", "description": "email address", "required": False},
49	            ],
50	            "max_pages": 1,
51	            "source_policy": "all_sources",
52	        },
53	    )
54	    job_id = res.json()["job_id"]

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_chennai.py:50:10
49	
50	    res = requests.post("http://localhost:8000/api/jobs", json=payload)
51	    res.raise_for_status()

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_chennai.py:56:26
55	        time.sleep(2)
56	        status_response = requests.get(f"http://localhost:8000/api/jobs/{job_id}")
57	        status_response.raise_for_status()

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:19:9
18	    }
19	    r1 = requests.post(f"{API}/api/jobs", json=payload)
20	    if r1.status_code != 200:

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:26:4
25	    time.sleep(1)
26	    requests.delete(f"{API}/api/jobs/{job_id}")
27	

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:28:9
27	
28	    r3 = requests.get(f"{API}/api/recycle_bin")
29	    [j["id"] for j in r3.json().get("jobs", [])]

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:31:4
30	
31	    requests.post(f"{API}/api/recycle_bin/{job_id}/restore")
32	

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:33:4
32	
33	    requests.delete(f"{API}/api/jobs/{job_id}")
34	

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:35:4
34	
35	    requests.delete(f"{API}/api/recycle_bin/{job_id}")
36	

--------------------------------------------------
>> Issue: [B113:request_without_timeout] Call to requests without timeout
   Severity: Medium   Confidence: Low
   CWE: CWE-400 (https://cwe.mitre.org/data/definitions/400.html)
   More Info: https://bandit.readthedocs.io/en/1.9.4/plugins/b113_request_without_timeout.html
   Location: backend/manual/manual_workflow.py:50:15
49	    }
50	    rcrawler = requests.post(f"{API}/api/jobs", json=payload2)
51	    rcrawler.raise_for_status()

--------------------------------------------------

Code scanned:
	Total lines of code: 62936
	Total lines skipped (#nosec): 1
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 44

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 0
		Medium: 12
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 12
		Medium: 0
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
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/postgres_repository.py:125
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
[manager]	WARNING	Test in comment: target is not a test name or id, ignoring
[manager]	WARNING	Test in comment: domains is not a test name or id, ignoring
[manager]	WARNING	Test in comment: may is not a test name or id, ignoring
[manager]	WARNING	Test in comment: use is not a test name or id, ignoring
[manager]	WARNING	Test in comment: self is not a test name or id, ignoring
[manager]	WARNING	Test in comment: signed is not a test name or id, ignoring
[manager]	WARNING	Test in comment: certs is not a test name or id, ignoring
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/scraper.py:267
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/storage_interface.py:460
[tester]	WARNING	nosec encountered (B608), but no failed test on file backend/app/storage_interface.py:543
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B104), but no failed test on file backend/app/url_safety.py:170
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:110
[tester]	WARNING	nosec encountered (B110), but no failed test on file backend/app/worker_queue_postgres_psycopg3.py:168
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
