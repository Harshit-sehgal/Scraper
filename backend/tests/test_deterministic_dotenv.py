import os
import sys
import importlib
from pathlib import Path
import pytest

def test_deterministic_dotenv_loading(tmp_path, monkeypatch):
    """Verify that importing/reloading app package loads backend/.env even when CWD is changed."""
    # Find the real backend directory
    backend_dir = Path(__file__).resolve().parents[2] / "backend"
    real_env = backend_dir / ".env"
    
    # Create a backup of the real .env if it exists
    env_content = ""
    if real_env.exists():
        env_content = real_env.read_text()
    
    # Temporarily append a dummy test variable to real .env
    test_key = "DATAFORGE_TEST_DETERMINISTIC_ENV_VAR"
    test_val = "loaded_successfully_from_real_backend"
    
    try:
        # Write to the backend/.env file
        with open(real_env, "a") as f:
            f.write(f"\n{test_key}={test_val}\n")
            
        # Change current working directory to isolated temp path
        monkeypatch.chdir(tmp_path)
        
        # Verify os.environ doesn't have the key yet
        monkeypatch.delenv(test_key, raising=False)
        assert test_key not in os.environ
        
        # Import app and reload to trigger app/__init__.py again
        import app
        importlib.reload(app)
        
        # Assert the variable was loaded successfully from backend/.env despite CWD change!
        assert os.environ.get(test_key) == test_val
    finally:
        # Restore the original .env content
        if real_env.exists():
            if env_content:
                real_env.write_text(env_content)
            else:
                real_env.unlink()
        monkeypatch.delenv(test_key, raising=False)
