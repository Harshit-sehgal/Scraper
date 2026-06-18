# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T11:55:46.623030+00:00
- end_time: 2026-06-12T11:59:13.197011+00:00
- duration_seconds: 206.57
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  2%]
........................................................................ [  4%]
........................................................................ [  6%]
..........F.F........................................................... [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
........................................................................ [ 14%]
........................................................................ [ 16%]
........................................................................ [ 18%]
........s............................................................... [ 20%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
.....................................................................sss [ 30%]
sssss................................................................... [ 32%]
..............................................................s......... [ 34%]
........s............................................................... [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
....ssssssssssssssssssssss...........................ss................. [ 50%]
....................................................ss.................. [ 53%]
....................F................................................... [ 55%]
........................................................................ [ 57%]
...................................................................sssss [ 59%]
ssssssss...................................s............................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
.................................sssssss................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
...................................................................s.... [ 95%]
...............ss..sssssssssssssssssss.................................. [ 97%]
........................................................................ [ 99%]
...                                                                      [100%]
=================================== FAILURES ===================================
___________________ TestAuthProfileModel.test_create_profile ___________________

self = <tests.test_auth_profiles.TestAuthProfileModel object at 0x73fda7b6a900>

    def test_create_profile(self):
        p = AuthProfile(name="Login for example.com", domain="example.com")
        assert p.name == "Login for example.com"
        assert p.domain == "example.com"
        assert p.status == AuthProfileStatus.ACTIVE
>       assert p.usage_count == 0
               ^^^^^^^^^^^^^

backend/tests/test_auth_profiles.py:17:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = AuthProfile(id='78230b4b-d0a3-46c2-b18b-c78cc8f1ec7b', name='Login for example.com', description='', user_id='', org_i...at=None, status='active', created_at='2026-06-12T11:56:06.054163+00:00', updated_at='2026-06-12T11:56:06.054170+00:00')
item = 'usage_count'

    def __getattr__(self, item: str) -> Any:
        private_attributes = object.__getattribute__(self, '__private_attributes__')
        if item in private_attributes:
            attribute = private_attributes[item]
            if hasattr(attribute, '__get__'):
                return attribute.__get__(self, type(self))  # type: ignore

            try:
                # Note: self.__pydantic_private__ cannot be None if self.__private_attributes__ has items
                return self.__pydantic_private__[item]  # type: ignore
            except KeyError as exc:
                raise AttributeError(f'{type(self).__name__!r} object has no attribute {item!r}') from exc
        else:
            # `__pydantic_extra__` can fail to be set if the model is not yet fully initialized.
            # See `BaseModel.__repr_args__` for more details
            try:
                pydantic_extra = object.__getattribute__(self, '__pydantic_extra__')
            except AttributeError:
                pydantic_extra = None

            if pydantic_extra and item in pydantic_extra:
                return pydantic_extra[item]
            else:
                if hasattr(self.__class__, item):
                    return super().__getattribute__(item)  # Raises AttributeError if appropriate
                else:
                    # this is the current error
>                   raise AttributeError(f'{type(self).__name__!r} object has no attribute {item!r}')
E                   AttributeError: 'AuthProfile' object has no attribute 'usage_count'

../../../../.local/lib/python3.12/site-packages/pydantic/main.py:1042: AttributeError
_____________ TestAuthProfileModel.test_storage_state_not_exposed ______________

self = <tests.test_auth_profiles.TestAuthProfileModel object at 0x73fda7b4e540>

    def test_storage_state_not_exposed(self):
        p = AuthProfile(name="Test", domain="test.com", encrypted_storage_state="secret")
        # Model should exist but the API endpoint strips this field
>       assert "storage_state" in p.model_dump()
E       AssertionError: assert 'storage_state' in {'created_at': '2026-06-12T11:56:06.111854+00:00', 'description': '', 'domain': 'test.com', 'encrypted_storage_state': 'secret', ...}
E        +  where {'created_at': '2026-06-12T11:56:06.111854+00:00', 'description': '', 'domain': 'test.com', 'encrypted_storage_state': 'secret', ...} = model_dump()
E        +    where model_dump = AuthProfile(id='7007c442-63bd-4976-82a4-e68779372ef5', name='Test', description='', user_id='', org_id='', project_id=...at=None, status='active', created_at='2026-06-12T11:56:06.111854+00:00', updated_at='2026-06-12T11:56:06.111858+00:00').model_dump

backend/tests/test_auth_profiles.py:26: AssertionError
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
E         app/models.py:566:1: redefinition of unused 'AuthProfile' from line 469
E         app/url_analyzer.py:478:5: local variable 'parsed' is assigned to but never used
E         app/routers/auth_profiles.py:18:1: 'app.models.AuthProfileStatus' imported but unused
E         app/saas/router.py:24:1: 'app.saas.models.User' imported but unused
E         app/saas/router.py:24:1: 'app.saas.models.UserStatus' imported but unused
E         tests/test_scheduled_monitoring.py:3:1: 'pytest' imported but unused
E         tests/test_auth_profiles.py:3:1: 'pytest' imported but unused
E
E
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pyflakes', 'app', 'tests'], returncode=1, stdout="app/models.py:566:...ring.py:3:1: 'pytest' imported but unused\ntests/test_auth_profiles.py:3:1: 'pytest' imported but unused\n", stderr='').returncode

backend/tests/test_pyflakes_fixes.py:20: AssertionError
=========================== short test summary info ============================
FAILED backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_create_profile
FAILED backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_storage_state_not_exposed
FAILED backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean - AssertionE...

```

## stderr

```text

```
