# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T01:24:19.049161+00:00
- end_time: 2026-06-17T01:24:19.089291+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
F401 [*] `pytest` imported but unused
  --> backend/tests/test_openapi_spec_contract.py:18:8
   |
16 | from pathlib import Path
17 |
18 | import pytest
   |        ^^^^^^
19 |
20 | REPO = Path(__file__).resolve().parents[2]
   |
help: Remove unused import: `pytest`

COM812 [*] Trailing comma missing
   --> scripts/analyze_code_complexity.py:201:107
    |
199 |         if sym["kind"] == "class" and sym["loc"] > max_class_loc:
200 |             violations.append(
201 |                 f"class `{sym['name']}` in {path}:{sym['lineno']} is {sym['loc']} LOC (> {max_class_loc})"
    |                                                                                                           ^
202 |             )
203 |         elif sym["kind"] == "function" and sym["loc"] > max_function_loc:
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> scripts/analyze_code_complexity.py:205:113
    |
203 |         elif sym["kind"] == "function" and sym["loc"] > max_function_loc:
204 |             violations.append(
205 |                 f"function `{sym['name']}` in {path}:{sym['lineno']} is {sym['loc']} LOC (> {max_function_loc})"
    |                                                                                                                 ^
206 |             )
207 |     for f in payload["largest_files"]:
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> scripts/analyze_code_complexity.py:213:70
    |
211 |         if f["loc"] > max_file_loc:
212 |             violations.append(
213 |                 f"file `{path}` is {f['loc']} LOC (> {max_file_loc})"
    |                                                                      ^
214 |             )
215 |     return violations
    |
help: Add trailing comma

S105 Possible hardcoded password assigned to: "DATAFORGE_SESSION_SECRET"
  --> scripts/generate_openapi.py:65:39
   |
63 |     env["DATAFORGE_OPERATOR_API_KEY"] = ""
64 |     env["DATAFORGE_ADMIN_API_KEY"] = ""
65 |     env["DATAFORGE_SESSION_SECRET"] = "openapi-gen-test-secret"
   |                                       ^^^^^^^^^^^^^^^^^^^^^^^^^
66 |     env["DATAFORGE_ALLOW_INSECURE_DEV_AUTH"] = "true"
67 |     env["DATAFORGE_SKIP_DB_CHECK"] = "true"
   |

EM102 Exception must not use an f-string literal, assign to variable first
  --> scripts/generate_openapi.py:78:13
   |
76 |       if result.returncode != 0:
77 |           raise RuntimeError(
78 | /             f"openapi generation failed (rc={result.returncode}):\n"
79 | |             f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
   | |_______________________________________________________________________________^
80 |           )
81 |       return json.loads(result.stdout)
   |
help: Assign to variable; remove f-string literal

COM812 [*] Trailing comma missing
  --> scripts/generate_openapi.py:79:80
   |
77 |         raise RuntimeError(
78 |             f"openapi generation failed (rc={result.returncode}):\n"
79 |             f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
   |                                                                                ^
80 |         )
81 |     return json.loads(result.stdout)
   |
help: Add trailing comma

PERF102 When using only the values of a dict use the `values()` method
  --> scripts/generate_openapi.py:87:23
   |
85 |     paths = spec.get("paths") or {}
86 |     by_method: dict[str, int] = {}
87 |     for _path, ops in paths.items():
   |                       ^^^^^^^^^^^
88 |         for method in ops.keys():
89 |             if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
   |
help: Replace `.items()` with `.values()`

SIM118 Use `key in dict` instead of `key in dict.keys()`
  --> scripts/generate_openapi.py:88:13
   |
86 |     by_method: dict[str, int] = {}
87 |     for _path, ops in paths.items():
88 |         for method in ops.keys():
   |             ^^^^^^^^^^^^^^^^^^^^
89 |             if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
90 |                 by_method[method.upper()] = by_method.get(method.upper(), 0) + 1
   |
help: Remove `.keys()`

COM812 [*] Trailing comma missing
   --> scripts/generate_openapi.py:145:41
    |
143 |         print(
144 |             f"  path_count={es['path_count']}  operation_count={es['operation_count']}"
145 |             f"  (+{diff_ops} vs stable)"
    |                                         ^
146 |         )
    |
help: Add trailing comma

Found 10 errors.
[*] 6 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```
