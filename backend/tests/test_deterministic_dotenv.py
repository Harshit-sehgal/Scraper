import importlib
import os


def test_deterministic_dotenv_loading(tmp_path, monkeypatch):
    """Verify app package loads the configured dotenv path even when CWD changes."""
    test_key = "DATAFORGE_TEST_DETERMINISTIC_ENV_VAR"
    test_val = "loaded_successfully_from_temp_dotenv"
    temp_env = tmp_path / ".env"
    temp_env.write_text(f"{test_key}={test_val}\n")
    isolated_cwd = tmp_path / "isolated-cwd"
    isolated_cwd.mkdir()

    monkeypatch.setenv("DATAFORGE_DOTENV_PATH", str(temp_env))
    monkeypatch.delenv(test_key, raising=False)
    monkeypatch.chdir(isolated_cwd)

    assert test_key not in os.environ

    import app
    importlib.reload(app)

    assert os.environ.get(test_key) == test_val
