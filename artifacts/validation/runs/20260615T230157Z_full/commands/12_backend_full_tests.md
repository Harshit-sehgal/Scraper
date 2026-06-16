# backend_full_tests

- status: failed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-15T23:02:13.186384+00:00
- end_time: 2026-06-15T23:06:23.297498+00:00
- duration_seconds: 250.11
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
..................s..................................................... [ 19%]
........................................................................ [ 21%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 27%]
........................................................................ [ 29%]
.............................................................ssssssss... [ 31%]
........................................................................ [ 33%]
......................................................s................. [ 35%]
s....................................................................... [ 37%]
........................................................................ [ 39%]
....FFFFFFFFFFFFF....................................................... [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
........................................................................ [ 49%]
............ssssssssssssssssssssss...........................ss......... [ 51%]
............................................................ss.......... [ 53%]
........................................................................ [ 55%]
........................................................................ [ 57%]
........................................................................ [ 59%]
...sssssssssssss...................................s.................... [ 61%]
........................................................................ [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
...............................................sssssss.................. [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
..........................................s...................ss..ssssss [ 96%]
sssssssssssss........................................................... [ 98%]
..........................................................               [100%]
=================================== FAILURES ===================================
______________ test_manual_script_import_safety[manual_test_api] _______________

module_name = 'manual_test_api'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_api', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_api'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_api'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_api': No module named 'manual_test_api'

backend/tests/test_manual_tests.py:49: Failed
___________ test_manual_script_import_safety[manual_test_app_scrape] ___________

module_name = 'manual_test_app_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_app_scrape'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_app_scrape'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_app_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_app_scrape': No module named 'manual_test_app_scrape'

backend/tests/test_manual_tests.py:49: Failed
____________ test_manual_script_import_safety[manual_test_chennai] _____________

module_name = 'manual_test_chennai'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_chennai', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_chennai'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_chennai'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_chennai': No module named 'manual_test_chennai'

backend/tests/test_manual_tests.py:49: Failed
____________ test_manual_script_import_safety[manual_test_extract] _____________

module_name = 'manual_test_extract'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_extract', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_extract'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_extract'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_extract': No module named 'manual_test_extract'

backend/tests/test_manual_tests.py:49: Failed
__________ test_manual_script_import_safety[manual_test_flights_e2e] ___________

module_name = 'manual_test_flights_e2e'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_flights_e2e'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_flights_e2e'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_flights_e2e'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_flights_e2e': No module named 'manual_test_flights_e2e'

backend/tests/test_manual_tests.py:49: Failed
_______________ test_manual_script_import_safety[manual_test_hn] _______________

module_name = 'manual_test_hn'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_hn', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_hn'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_hn'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_hn': No module named 'manual_test_hn'

backend/tests/test_manual_tests.py:49: Failed
____________ test_manual_script_import_safety[manual_test_insight] _____________

module_name = 'manual_test_insight'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_insight', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_insight'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_insight'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_insight': No module named 'manual_test_insight'

backend/tests/test_manual_tests.py:49: Failed
_____________ test_manual_script_import_safety[manual_test_modes] ______________

module_name = 'manual_test_modes'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_modes', import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_modes'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_modes'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_modes': No module named 'manual_test_modes'

backend/tests/test_manual_tests.py:49: Failed
__________ test_manual_script_import_safety[manual_test_pollinations] __________

module_name = 'manual_test_pollinations'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_pollinations'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_pollinations'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_pollinations'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_pollinations': No module named 'manual_test_pollinations'

backend/tests/test_manual_tests.py:49: Failed
___________ test_manual_script_import_safety[manual_test_providers] ____________

module_name = 'manual_test_providers'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_providers'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_providers'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_providers'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_providers': No module named 'manual_test_providers'

backend/tests/test_manual_tests.py:49: Failed
__________ test_manual_script_import_safety[manual_test_real_scrape] ___________

module_name = 'manual_test_real_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_real_scrape'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_real_scrape'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_real_scrape'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_real_scrape': No module named 'manual_test_real_scrape'

backend/tests/test_manual_tests.py:49: Failed
_________ test_manual_script_import_safety[manual_test_threebestrated] _________

module_name = 'manual_test_threebestrated'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_threebestrated'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_threebestrated'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_threebestrated'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_threebestrated': No module named 'manual_test_threebestrated'

backend/tests/test_manual_tests.py:49: Failed
____________ test_manual_script_import_safety[manual_test_workflow] ____________

module_name = 'manual_test_workflow'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
>           mod = importlib.import_module(module_name)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

backend/tests/test_manual_tests.py:46: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

name = 'manual_test_workflow'
import_ = <function _gcd_import at 0x7579fc9800e0>

>   ???
E   ModuleNotFoundError: No module named 'manual_test_workflow'

<frozen importlib._bootstrap>:1324: ModuleNotFoundError

During handling of the above exception, another exception occurred:

module_name = 'manual_test_workflow'

    @pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
    def test_manual_script_import_safety(module_name) -> None:
        """Import manual test modules dynamically to assert that they are syntactically.
    
        correct and have no side effects (e.g. blocking HTTP calls or database actions
        on import).
        """
        # Ensure backend/tests is in path
        tests_dir = str(Path(__file__).parent)
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
    
        try:
            # Dyn import the module
            mod = importlib.import_module(module_name)
            assert mod is not None
        except Exception as e:
>           pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")
E           Failed: Failed to safely import manual test module 'manual_test_workflow': No module named 'manual_test_workflow'

backend/tests/test_manual_tests.py:49: Failed
=========================== short test summary info ============================
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_api]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_app_scrape]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_chennai]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_extract]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_flights_e2e]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_hn]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_insight]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_modes]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_pollinations]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_providers]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_real_scrape]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_threebestrated]
FAILED backend/tests/test_manual_tests.py::test_manual_script_import_safety[manual_test_workflow]

```

## stderr

```text

```
