# backend_full_tests

- status: passed
- command: `/usr/bin/python3 -m pytest backend/tests -q`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-13T04:01:56.145868+00:00
- end_time: 2026-06-13T04:06:04.924139+00:00
- duration_seconds: 248.78
- exit_code: 0
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
..........................................................ssssssss...... [ 31%]
........................................................................ [ 33%]
...................................................s.................s.. [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
........................................................................ [ 49%]
.........ssssssssssssssssssssss...........................ss............ [ 51%]
.........................................................ss............. [ 53%]
........................................................................ [ 55%]
........................................................................ [ 57%]
........................................................................ [ 59%]
sssssssssssss...................................s....................... [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
..........................................sssssss....................... [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
..................................s...................ss..ssssssssssssss [ 96%]
sssss................................................................... [ 98%]
.................................................                        [100%]
=============================== warnings summary ===============================
backend/tests/test_pagination_async.py::TestAsyncPaginateNextButton::test_single_page_no_next_button
backend/tests/test_pagination_async.py::TestAsyncPaginateNextButton::test_respects_max_pages
backend/tests/test_pagination_async.py::TestAsyncPaginateNextButton::test_respects_max_records
backend/tests/test_pagination_async.py::TestAsyncPaginateEdgeCases::test_empty_extract_fn
backend/tests/test_pagination_async.py::TestAsyncPaginateEdgeCases::test_extraction_function_error
  /home/harshit/Documents/Work/Money/scraper/backend/app/pagination_executor.py:177: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    continue
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

backend/tests/test_pagination_async.py::TestAsyncPaginateLoadMore::test_no_load_more_button
backend/tests/test_pagination_async.py::TestAsyncPaginateLoadMore::test_load_more_respects_max_pages
  /home/harshit/Documents/Work/Money/scraper/backend/app/pagination_executor.py:323: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    continue
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

backend/tests/test_pagination_async.py::TestAsyncPaginatePageNumber::test_single_page_no_pagination_links
  /home/harshit/Documents/Work/Money/scraper/backend/app/pagination_executor.py:421: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    links = page.locator(sel)
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

backend/tests/test_pagination_async.py::TestAsyncPaginatePageNumber::test_single_page_no_pagination_links
  /home/harshit/Documents/Work/Money/scraper/backend/app/pagination_executor.py:596: RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
    return await strategy_fn(page, config, extract_fn, base_url=base_url)
  Enable tracemalloc to get traceback where the object was allocated.
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

```

## stderr

```text

```
