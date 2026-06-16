"""Manual exploratory scripts.

These files are not pytest tests. They are exploratory / smoke scripts
that hit a running DataForge API over HTTP. They are kept here (out of
``backend/tests/``) so that:

- pytest's default discovery (``python_files = ["test_*.py"]``) does
  not pick them up.
- They do not contribute to coverage or per-file lint configurations
  intended for the automated test suite.
- They can still be imported and statically validated by
  ``backend/tests/test_manual_tests.py`` (which asserts that every
  script imports cleanly with no top-level side effects).
"""
