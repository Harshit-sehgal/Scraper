# p0_regression_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T16:17:35.684020+00:00
- end_time: 2026-06-12T16:17:36.831597+00:00
- duration_seconds: 1.15
- exit_code: 3
- timeout_seconds: 180
- required: true
- redaction_applied: false

## stdout

```text

```

## stderr

```text
INTERNALERROR> Traceback (most recent call last):
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/main.py", line 314, in wrap_session
INTERNALERROR>     config._do_configure()
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/_pytest/config/__init__.py", line 1165, in _do_configure
INTERNALERROR>     self.hook.pytest_configure.call_historic(kwargs=dict(config=self))
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_hooks.py", line 534, in call_historic
INTERNALERROR>     res = self._hookexec(self.name, self._hookimpls.copy(), kwargs, False)
INTERNALERROR>           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
INTERNALERROR>     return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
INTERNALERROR>            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 167, in _multicall
INTERNALERROR>     raise exception
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
INTERNALERROR>     res = hook_impl.function(*args)
INTERNALERROR>           ^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pytest_rerunfailures.py", line 386, in pytest_configure
INTERNALERROR>     config.failures_db = ServerStatusDB()
INTERNALERROR>                          ^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pytest_rerunfailures.py", line 490, in __init__
INTERNALERROR>     super().__init__()
INTERNALERROR>   File "/home/harshit/.local/lib/python3.12/site-packages/pytest_rerunfailures.py", line 471, in __init__
INTERNALERROR>     self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
INTERNALERROR>                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
INTERNALERROR>   File "/usr/lib/python3.12/socket.py", line 233, in __init__
INTERNALERROR>     _socket.socket.__init__(self, family, type, proto, fileno)
INTERNALERROR> PermissionError: [Errno 1] Operation not permitted

```
