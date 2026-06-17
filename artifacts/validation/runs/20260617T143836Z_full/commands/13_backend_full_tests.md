# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-17T14:38:53.016039+00:00
- end_time: 2026-06-17T14:43:19.946935+00:00
- duration_seconds: 266.93
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
........................................................................ [  5%]
.............................................ss......................... [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
................................s....................................... [ 19%]
........................................................................ [ 21%]
...........................................................F............ [ 23%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
.......ssssssss......................................................... [ 32%]
........................................................................ [ 34%]
s.................s..................................................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 47%]
.....................................................................sss [ 49%]
sssssssssssssssssss...........................ss........................ [ 51%]
.................................................ss..................... [ 53%]
.................F...................................................... [ 55%]
........................................................................ [ 57%]
................................................................ssssssss [ 59%]
sssss...................................s............................... [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
..........ss............................................................ [ 69%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
.......................................................sssssss.......... [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 93%]
......................................................s................. [ 95%]
..ss..sssssssssssssssssss............................................... [ 97%]
........................................................................ [ 99%]
...........                                                              [100%]
=================================== FAILURES ===================================
_______ TestBatchExportErrors.test_batch_unsupported_format_returns_400 ________

self = <tests.test_exports_router.TestBatchExportErrors object at 0x7c7187bbc740>

    @pytest.mark.asyncio
    async def test_batch_unsupported_format_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient
    
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["j1"] = _make_job("j1", results=[{"x": "1"}])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["j1"], "format": "xml"},
            )
>       assert resp.status_code == 400
E       assert 422 == 400
E        +  where 422 = <Response [422 Unprocessable Entity]>.status_code

backend/tests/test_exports_router.py:810: AssertionError
_____________________________ test_pyflakes_clean ______________________________

    def test_pyflakes_clean() -> None:
        """Run pyflakes programmatically over backend/app and backend/tests and assert no warnings or errors."""
        # Resolve the absolute path to the backend directory dynamically
        backend_dir = Path(__file__).resolve().parents[1]
    
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", "app", "tests"],
            cwd=str(backend_dir),
            text=True,
            capture_output=True,
        )
    
>       assert result.returncode == 0, f"Pyflakes validation failed with warnings/errors:\n{result.stdout}\n{result.stderr}"
E       AssertionError: Pyflakes validation failed with warnings/errors:
E         app/routers/auth_profiles.py:265:51: undefined name 'settings'
E         app/routers/auth_profiles.py:265:20: undefined name 'settings'
E         
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pyflakes', 'app', 'tests'], returncode=1, stdout="app/routers/auth_p...les.py:265:51: undefined name 'settings'\napp/routers/auth_profiles.py:265:20: undefined name 'settings'\n", stderr='').returncode

backend/tests/test_pyflakes_fixes.py:20: AssertionError
=============================== warnings summary ===============================
backend/app/routers/exports.py:61
  /home/harshit/Documents/Work/Money/scraper/backend/app/routers/exports.py:61: PydanticDeprecatedSince20: Pydantic V1 style `@validator` validators are deprecated. You should migrate to Pydantic V2 style `@field_validator` validators, see the migration guide for more details. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    @validator("format")

backend/tests/test_pagination_async.py::TestCanonicalFiveStrategyContract::test_strategy_enum_strings_match_across_layers
  backend/tests/test_pagination_async.py:510: PytestWarning: The test <Function test_strategy_enum_strings_match_across_layers> is marked with '@pytest.mark.asyncio' but it is not an async function. Please remove the asyncio mark. If the test is not marked explicitly, check for global marks applied via 'pytestmark'.
    def test_strategy_enum_strings_match_across_layers(self) -> None:

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED backend/tests/test_exports_router.py::TestBatchExportErrors::test_batch_unsupported_format_returns_400
FAILED backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean - AssertionE...

```

## stderr

```text

```
