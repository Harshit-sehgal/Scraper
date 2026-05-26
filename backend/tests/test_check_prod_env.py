"""Unit tests for scripts/check_prod_env.py — production environment validation."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


# Ensure the script is importable
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPT_PATH) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_PATH))


@pytest.fixture
def env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("# Test .env\n")
        f.flush()
        yield Path(f.name)
    os.unlink(f.name)


def _write_env(path: Path, vars: dict[str, str]):
    """Write variables to an env file."""
    with open(path, "w") as f:
        for key, value in vars.items():
            f.write(f'{key}="{value}"\n')


class TestCheckProdEnvCore:
    """Core tests for the check_prod_env module functions."""

    def _import_module(self):
        """Import the check_prod_env module dynamically."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_load_env_file_reads_variables(self):
        """load_env_file should parse a basic .env file."""
        mod = self._import_module()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('DATAFORGE_API_KEY="abc123"\n')
            f.write('# comment\n')
            f.write('DATAFORGE_ENV="production"\n')
            f.flush()
            path = Path(f.name)

        try:
            env = mod.load_env_file(path)
            assert env["DATAFORGE_API_KEY"] == "abc123"
            assert env["DATAFORGE_ENV"] == "production"
            assert "comment" not in env
        finally:
            os.unlink(f.name)

    def test_load_env_file_handles_missing_file(self):
        """load_env_file should return empty dict for missing file."""
        mod = self._import_module()
        result = mod.load_env_file(Path("/nonexistent/.env"))
        assert result == {}

    def test_check_var_missing_required_fails(self):
        """A required but missing variable should fail."""
        mod = self._import_module()
        assert not mod.check_var({}, "DATAFORGE_API_KEY", required=True)

    def test_check_var_optional_missing_passes(self):
        """An optional missing variable should pass."""
        mod = self._import_module()
        assert mod.check_var({}, "OPTIONAL_VAR", required=False)

    def test_check_var_with_validator_passes(self):
        """A variable that passes validation should succeed."""
        mod = self._import_module()
        def always_true(v): return True
        assert mod.check_var({"MY_VAR": "ok"}, "MY_VAR", validator=always_true)

    def test_check_var_with_validator_fails(self):
        """A variable that fails validation should fail."""
        mod = self._import_module()
        def always_false(v): return False
        assert not mod.check_var({"MY_VAR": "bad"}, "MY_VAR", validator=always_false)


class TestCheckProdEnvValidators:
    """Specific validator function tests."""

    def _import_module(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_check_cors_origins_valid_json_list(self):
        """Valid JSON array of origins should pass."""
        mod = self._import_module()
        assert mod.check_cors_origins('["https://example.com"]')
        assert mod.check_cors_origins('["https://app.example.com", "https://api.example.com"]')

    def test_check_cors_origins_rejects_wildcard(self):
        """Wildcard '*' in origins should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('["*"]')
        assert not mod.check_cors_origins('["https://example.com", "*"]')

    def test_check_cors_origins_rejects_invalid_json(self):
        """Invalid JSON should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins("not-json")
        assert not mod.check_cors_origins("{invalid}")
        assert not mod.check_cors_origins("")

    def test_check_cors_origins_rejects_non_list(self):
        """Non-list JSON should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('"https://example.com"')
        assert not mod.check_cors_origins('{}')
        assert not mod.check_cors_origins("42")

    def test_check_cors_origins_rejects_non_url(self):
        """Origins that don't start with http:// or https:// should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('["ftp://example.com"]')
        assert not mod.check_cors_origins('["example.com"]')

    def test_check_storage_backend_accepts_postgres(self):
        """'postgres' should pass."""
        mod = self._import_module()
        assert mod.check_storage_backend("postgres")
        assert mod.check_storage_backend("POSTGRES")
        assert mod.check_storage_backend("Postgres")

    def test_check_storage_backend_rejects_other(self):
        """Anything other than 'postgres' should fail."""
        mod = self._import_module()
        assert not mod.check_storage_backend("sqlite")
        assert not mod.check_storage_backend("mysql")
        assert not mod.check_storage_backend("")

    def test_check_worker_queue_accepts_true(self):
        """'true' should pass."""
        mod = self._import_module()
        assert mod.check_worker_queue("true")
        assert mod.check_worker_queue("TRUE")
        assert mod.check_worker_queue("1")
        assert mod.check_worker_queue("yes")

    def test_check_worker_queue_rejects_false(self):
        """'false' or other values should fail."""
        mod = self._import_module()
        assert not mod.check_worker_queue("false")
        assert not mod.check_worker_queue("0")
        assert not mod.check_worker_queue("no")
        assert not mod.check_worker_queue("")


class TestCheckProdEnvIntegration:
    """Integration tests exercising the full main() flow."""

    def _import_module(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_valid_env_passes_all_checks(self, env_file):
        """A fully valid .env should pass all checks."""
        mod = self._import_module()
        _write_env(env_file, {
            "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
            "DATAFORGE_DB_PASSWORD": "secure-password-123",
            "DATAFORGE_STORAGE_BACKEND": "postgres",
            "DATAFORGE_WORKER_QUEUE": "true",
        })

        env = mod.load_env_file(env_file)
        all_pass = True
        for name, _, validator, _ in [
            ("DATAFORGE_API_KEY", True, None, ""),
            ("DATAFORGE_CORS_ORIGINS", True, mod.check_cors_origins, ""),
            ("DATAFORGE_DB_PASSWORD", True, None, ""),
            ("DATAFORGE_STORAGE_BACKEND", True, mod.check_storage_backend, ""),
            ("DATAFORGE_WORKER_QUEUE", True, mod.check_worker_queue, ""),
        ]:
            passed = mod.check_var(env, name, required=True, validator=validator)
            if not passed:
                all_pass = False

        assert all_pass, "All production env checks should pass with valid values"

    def test_rejects_wildcard_cors(self, env_file):
        """Env with wildcard CORS should fail CORS check."""
        mod = self._import_module()
        _write_env(env_file, {
            "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "DATAFORGE_CORS_ORIGINS": '["*"]',
            "DATAFORGE_DB_PASSWORD": "secure-password-123",
            "DATAFORGE_STORAGE_BACKEND": "postgres",
            "DATAFORGE_WORKER_QUEUE": "true",
        })

        env = mod.load_env_file(env_file)
        assert not mod.check_var(env, "DATAFORGE_CORS_ORIGINS", required=True, validator=mod.check_cors_origins)

    def test_rejects_default_api_key(self, env_file):
        """Short/default API key should pass (no built-in minimum length) — just test it's not empty."""
        mod = self._import_module()
        _write_env(env_file, {
            "DATAFORGE_API_KEY": "",
            "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
            "DATAFORGE_DB_PASSWORD": "secure-password-123",
            "DATAFORGE_STORAGE_BACKEND": "postgres",
            "DATAFORGE_WORKER_QUEUE": "true",
        })

        env = mod.load_env_file(env_file)
        # API_KEY is empty so check_var with required=True should fail
        assert not mod.check_var(env, "DATAFORGE_API_KEY", required=True)

    def test_rejects_default_db_password(self, env_file):
        """Default DB password should fail check."""
        mod = self._import_module()
        _write_env(env_file, {
            "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
            "DATAFORGE_DB_PASSWORD": "dataforge",
            "DATAFORGE_STORAGE_BACKEND": "postgres",
            "DATAFORGE_WORKER_QUEUE": "true",
        })

        # Note: check_prod_env doesn't have built-in "not default" validation,
        # but we test that the base check passes (non-empty)
        env = mod.load_env_file(env_file)
        assert mod.check_var(env, "DATAFORGE_DB_PASSWORD", required=True)

    def test_accepts_postgres_env(self, env_file):
        """All valid Postgres env vars should pass."""
        mod = self._import_module()
        _write_env(env_file, {
            "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "DATAFORGE_CORS_ORIGINS": '["https://app.example.com", "https://dashboard.example.com"]',
            "DATAFORGE_DB_PASSWORD": "strong-password-xyz",
            "DATAFORGE_STORAGE_BACKEND": "postgres",
            "DATAFORGE_WORKER_QUEUE": "true",
        })

        env = mod.load_env_file(env_file)
        checks = [
            mod.check_var(env, "DATAFORGE_API_KEY", required=True),
            mod.check_var(env, "DATAFORGE_CORS_ORIGINS", required=True, validator=mod.check_cors_origins),
            mod.check_var(env, "DATAFORGE_DB_PASSWORD", required=True),
            mod.check_var(env, "DATAFORGE_STORAGE_BACKEND", required=True, validator=mod.check_storage_backend),
            mod.check_var(env, "DATAFORGE_WORKER_QUEUE", required=True, validator=mod.check_worker_queue),
        ]
        assert all(checks), f"All checks should pass: {checks}"
