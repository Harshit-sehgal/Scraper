# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-16T18:34:56.396052+00:00
- end_time: 2026-06-16T18:39:09.040215+00:00
- duration_seconds: 252.65
- exit_code: 1
- timeout_seconds: 600
- required: true
- redaction_applied: false

## stdout

```text
........................................................................ [  1%]
........................................................................ [  3%]
........................................................................ [  5%]
........................................................................ [  7%]
........................................................................ [  9%]
........................................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 15%]
........................................................................ [ 17%]
............................s........................................... [ 19%]
........................................................................ [ 21%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
........................................................................ [ 31%]
...ssssssss............................................................. [ 33%]
....................................................................s... [ 35%]
..............s......................................................... [ 37%]
........................................................................ [ 39%]
.................FFFFFFFFFFFFF.......................................... [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 48%]
..........................................ssssssssssssssssssssss........ [ 50%]
...................ss................................................... [ 52%]
......................ss......................................F......... [ 54%]
........................................................................ [ 56%]
........................................................................ [ 58%]
.....................................sssssssssssss...................... [ 60%]
.............s.......................................................... [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 79%]
........................................................................ [ 81%]
.........sssssss........................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
....s...................ss..sssssssssssssssssss......................... [ 97%]
........................................................................ [ 99%]
....................                                                     [100%]
=================================== FAILURES ===================================
_________________ test_manual_script_import_safety[manual_api] _________________

module_name = 'manual_api'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_api', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_api'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_api'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_api': No module named 'manual_api'

backend/tests/test_manual_tests.py:56: Failed
_____________ test_manual_script_import_safety[manual_app_scrape] ______________

module_name = 'manual_app_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_app_scrape', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_app_scrape'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_app_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_app_scrape': No module named 'manual_app_scrape'

backend/tests/test_manual_tests.py:56: Failed
_______________ test_manual_script_import_safety[manual_chennai] _______________

module_name = 'manual_chennai'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_chennai', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_chennai'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_chennai'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_chennai': No module named 'manual_chennai'

backend/tests/test_manual_tests.py:56: Failed
_______________ test_manual_script_import_safety[manual_extract] _______________

module_name = 'manual_extract'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_extract', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_extract'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_extract'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_extract': No module named 'manual_extract'

backend/tests/test_manual_tests.py:56: Failed
_____________ test_manual_script_import_safety[manual_flights_e2e] _____________

module_name = 'manual_flights_e2e'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_flights_e2e', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_flights_e2e'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_flights_e2e'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_flights_e2e': No module named 'manual_flights_e2e'

backend/tests/test_manual_tests.py:56: Failed
_________________ test_manual_script_import_safety[manual_hn] __________________

module_name = 'manual_hn'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_hn', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_hn'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_hn'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_hn': No module named 'manual_hn'

backend/tests/test_manual_tests.py:56: Failed
_______________ test_manual_script_import_safety[manual_insight] _______________

module_name = 'manual_insight'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_insight', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_insight'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_insight'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_insight': No module named 'manual_insight'

backend/tests/test_manual_tests.py:56: Failed
________________ test_manual_script_import_safety[manual_modes] ________________

module_name = 'manual_modes'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_modes', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_modes'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_modes'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_modes': No module named 'manual_modes'

backend/tests/test_manual_tests.py:56: Failed
____________ test_manual_script_import_safety[manual_pollinations] _____________

module_name = 'manual_pollinations'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_pollinations', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_pollinations'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_pollinations'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_pollinations': No module named 'manual_pollinations'

backend/tests/test_manual_tests.py:56: Failed
______________ test_manual_script_import_safety[manual_providers] ______________

module_name = 'manual_providers'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_providers', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_providers'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_providers'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_providers': No module named 'manual_providers'

backend/tests/test_manual_tests.py:56: Failed
_____________ test_manual_script_import_safety[manual_real_scrape] _____________

module_name = 'manual_real_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_real_scrape', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_real_scrape'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_real_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_real_scrape': No module named 'manual_real_scrape'

backend/tests/test_manual_tests.py:56: Failed
___________ test_manual_script_import_safety[manual_threebestrated] ____________

module_name = 'manual_threebestrated'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_threebestrated'
import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_threebestrated'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_threebestrated'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_threebestrated': No module named 'manual_threebestrated'

backend/tests/test_manual_tests.py:56: Failed
______________ test_manual_script_import_safety[manual_workflow] _______________

module_name = 'manual_workflow'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:53:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

name = 'manual_workflow', import_ = <function _gcd_import at 0x753404cdc0e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_workflow'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_workflow'

    @pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
    def test_manual_script_import_safety(module_name) -> None:
        """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as exc:
>           pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")
E           Failed: Failed to safely import manual script 'manual_workflow': No module named 'manual_workflow'

backend/tests/test_manual_tests.py:56: Failed
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
E         tests/test_plan_enforcer_unknown_tier.py:87:9: local variable '_fake_get_user_tier_from_billing' is assigned to but never used
E
E
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/usr/bin/python3', '-m', 'pyflakes', 'app', 'tests'], returncode=1, stdout="tests/test_plan_en...er_unknown_tier.py:87:9: local variable '_fake_get_user_tier_from_billing' is assigned to but never used\n", stderr='').returncode

backend/tests/test_pyflakes_fixes.py:20: AssertionError
=========================== short test summary info ============================
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_api]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_app_scrape]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_chennai]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_extract]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_flights_e2e]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_hn]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_insight]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_modes]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_pollinations]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_providers]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_real_scrape]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_threebestrated]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_workflow]
FAILED backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean - AssertionE...

```

## stderr

```text

```
