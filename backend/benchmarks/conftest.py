import os
import sys

# Inherit pytest options and hooks from backend/tests/conftest.py to ensure unified execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests")))
