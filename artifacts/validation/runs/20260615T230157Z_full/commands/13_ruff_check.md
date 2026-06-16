# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-15T23:06:23.300272+00:00
- end_time: 2026-06-15T23:06:23.330705+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_api.py:10:15
   |
 8 | def wait_for_job(job_id) -> None:
 9 |     for _ in range(60):
10 |         res = requests.get(f"{BASE_URL}/api/jobs/{job_id}")
   |               ^^^^^^^^^^^^
11 |         data = res.json()
12 |         if data["status"] in ["completed", "failed", "canceled"]:
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_api.py:18:11
   |
17 | def test_manual() -> None:
18 |     res = requests.post(
   |           ^^^^^^^^^^^^^
19 |         f"{BASE_URL}/api/jobs",
20 |         json={
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_api.py:38:11
   |
37 | def test_auto() -> None:
38 |     res = requests.post(
   |           ^^^^^^^^^^^^^
39 |         f"{BASE_URL}/api/jobs",
40 |         json={
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_chennai.py:50:11
   |
48 |     }
49 |
50 |     res = requests.post("http://localhost:8000/api/jobs", json=payload)
   |           ^^^^^^^^^^^^^
51 |     res.raise_for_status()
52 |     job_id = res.json()["job_id"]
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_chennai.py:56:27
   |
54 |     while True:
55 |         time.sleep(2)
56 |         status_response = requests.get(f"http://localhost:8000/api/jobs/{job_id}")
   |                           ^^^^^^^^^^^^
57 |         status_response.raise_for_status()
58 |         status = status_response.json()
   |

ASYNC240 Async functions should not use pathlib.Path methods, use trio.Path or anyio.path
  --> backend/manual/manual_flights_e2e.py:52:46
   |
50 |     import os
51 |
52 |     os.environ["DATAFORGE_STATE_FILE"] = str(Path(__file__).resolve().parent.parent / "data" / "jobs_state_test.json")
   |                                              ^^^^^^^^^^^^^^^^^^^^^^
53 |
54 |     url = (
   |

LOG015 `exception()` call on root logger
  --> backend/manual/manual_pollinations.py:47:9
   |
45 |         import logging
46 |
47 |         logging.exception("Pollinations API test failed")
   |         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   |
help: Use own logger instead

LOG015 `exception()` call on root logger
  --> backend/manual/manual_providers.py:17:9
   |
15 |         import logging
16 |
17 |         logging.exception("Provider test failed")
   |         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
18 |         return False
   |
help: Use own logger instead

ASYNC230 Async functions should not open files with blocking methods like `open`
  --> backend/manual/manual_threebestrated.py:80:14
   |
78 |                 unique_designers.append(b)
79 |
80 |         with open(
   |              ^^^^
81 |             "/home/harshit/Documents/Work/Money/scraper/chennai_interior_designers.csv",
82 |             "w",
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:19:10
   |
17 |         "max_pages": 1,
18 |     }
19 |     r1 = requests.post(f"{API}/api/jobs", json=payload)
   |          ^^^^^^^^^^^^^
20 |     if r1.status_code != 200:
21 |         msg = f"Error: {r1.text}"
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:26:5
   |
25 |     time.sleep(1)
26 |     requests.delete(f"{API}/api/jobs/{job_id}")
   |     ^^^^^^^^^^^^^^^
27 |
28 |     r3 = requests.get(f"{API}/api/recycle_bin")
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:28:10
   |
26 |     requests.delete(f"{API}/api/jobs/{job_id}")
27 |
28 |     r3 = requests.get(f"{API}/api/recycle_bin")
   |          ^^^^^^^^^^^^
29 |     [j["id"] for j in r3.json().get("jobs", [])]
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:31:5
   |
29 |     [j["id"] for j in r3.json().get("jobs", [])]
30 |
31 |     requests.post(f"{API}/api/recycle_bin/{job_id}/restore")
   |     ^^^^^^^^^^^^^
32 |
33 |     requests.delete(f"{API}/api/jobs/{job_id}")
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:33:5
   |
31 |     requests.post(f"{API}/api/recycle_bin/{job_id}/restore")
32 |
33 |     requests.delete(f"{API}/api/jobs/{job_id}")
   |     ^^^^^^^^^^^^^^^
34 |
35 |     requests.delete(f"{API}/api/recycle_bin/{job_id}")
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:35:5
   |
33 |     requests.delete(f"{API}/api/jobs/{job_id}")
34 |
35 |     requests.delete(f"{API}/api/recycle_bin/{job_id}")
   |     ^^^^^^^^^^^^^^^
36 |
37 |     payload2: Any = {
   |

S113 Probable use of `requests` call without timeout
  --> backend/manual/manual_workflow.py:50:16
   |
48 |         ],
49 |     }
50 |     rcrawler = requests.post(f"{API}/api/jobs", json=payload2)
   |                ^^^^^^^^^^^^^
51 |     rcrawler.raise_for_status()
52 |     rcrawler.json()["job_id"]
   |

Found 16 errors.

```

## stderr

```text

```
