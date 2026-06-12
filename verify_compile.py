#!/usr/bin/env python3
"""Quick compile check for Phase 3 URL Intelligence files."""

import py_compile
import sys

files = [
    "backend/app/url_analyzer.py",
    "backend/app/routers/intelligence.py",
    "backend/app/routers/system.py",
    "backend/tests/test_url_analyzer.py",
]

all_ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError:
        all_ok = False

if all_ok:
    sys.exit(0)
else:
    sys.exit(1)
