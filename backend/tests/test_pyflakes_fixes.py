"""
Verify there are no unresolved pyflakes warnings across the codebase.
"""

import subprocess
import sys
from pathlib import Path


def test_pyflakes_clean():
    """Run pyflakes programmatically over backend/app and backend/tests and assert no warnings or errors."""
    # Resolve the absolute path to the backend directory dynamically
    backend_dir = Path(__file__).resolve().parents[1]
    
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", "app", "tests"],
        cwd=str(backend_dir),
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, f"Pyflakes validation failed with warnings/errors:\n{result.stdout}\n{result.stderr}"
