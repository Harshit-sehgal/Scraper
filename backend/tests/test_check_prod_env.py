"""Unit tests for scripts/check_prod_env.py — production environment validation."""

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


def _write_env(path: Path, vars: dict[str, str]) -> None:
    """Write variables to an env file."""
    with open(path, "w") as f:
        f.writelines(f'{key}="{value}"\n' for key, value in vars.items())


class TestCheckProdEnvCore:
    """Core tests for the check_prod_env module functions."""

    def _import_module(self):
        """Import the check_prod_env module dynamically."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_load_env_file_reads_variables(self) -> None:
        """load_env_file should parse a basic .env file."""
        mod = self._import_module()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('DATAFORGE_API_KEY="abc123"\n')
            f.write("# comment\n")
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

    def test_load_env_file_handles_missing_file(self) -> None:
        """load_env_file should return empty dict for missing file."""
        mod = self._import_module()
        result = mod.load_env_file(Path("/nonexistent/.env"))
        assert result == {}

    def test_check_var_missing_required_fails(self) -> None:
        """A required but missing variable should fail."""
        mod = self._import_module()
        assert not mod.check_var({}, "DATAFORGE_API_KEY", required=True)

    def test_check_var_optional_missing_passes(self) -> None:
        """An optional missing variable should pass."""
        mod = self._import_module()
        assert mod.check_var({}, "OPTIONAL_VAR", required=False)

    def test_check_var_with_validator_passes(self) -> None:
        """A variable that passes validation should succeed."""
        mod = self._import_module()

        def always_true(v) -> bool:
            return True

        assert mod.check_var({"MY_VAR": "ok"}, "MY_VAR", validator=always_true)

    def test_check_var_with_validator_fails(self) -> None:
        """A variable that fails validation should fail."""
        mod = self._import_module()

        def always_false(v) -> bool:
            return False

        assert not mod.check_var({"MY_VAR": "bad"}, "MY_VAR", validator=always_false)

    def test_mask_value_redacts_database_url_password(self) -> None:
        """Database URLs should not print credentials in validation output."""
        mod = self._import_module()
        masked = mod._mask_value(
            "DATAFORGE_DATABASE_URL",
            "postgresql://dataforge:strong-password-123@postgres:5432/dataforge",
        )
        assert "strong-password-123" not in masked
        assert masked == "postgresql://dataforge:****@postgres:5432/dataforge"


class TestCheckProdEnvValidators:
    """Specific validator function tests."""

    def _import_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_check_cors_origins_valid_json_list(self) -> None:
        """Valid JSON array of origins should pass."""
        mod = self._import_module()
        assert mod.check_cors_origins('["https://example.com"]')
        assert mod.check_cors_origins('["https://app.example.com", "https://api.example.com"]')

    def test_check_cors_origins_rejects_wildcard(self) -> None:
        """Wildcard '*' in origins should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('["*"]')
        assert not mod.check_cors_origins('["https://example.com", "*"]')

    def test_check_cors_origins_rejects_invalid_json(self) -> None:
        """Invalid JSON should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins("not-json")
        assert not mod.check_cors_origins("{invalid}")
        assert not mod.check_cors_origins("")

    def test_check_cors_origins_rejects_non_list(self) -> None:
        """Non-list JSON should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('"https://example.com"')
        assert not mod.check_cors_origins("{}")
        assert not mod.check_cors_origins("42")

    def test_check_cors_origins_rejects_non_url(self) -> None:
        """Origins that don't start with http:// or https:// should fail."""
        mod = self._import_module()
        assert not mod.check_cors_origins('["ftp://example.com"]')
        assert not mod.check_cors_origins('["example.com"]')

    def test_check_storage_backend_accepts_postgres(self) -> None:
        """'postgres' should pass."""
        mod = self._import_module()
        assert mod.check_storage_backend("postgres")
        assert mod.check_storage_backend("POSTGRES")
        assert mod.check_storage_backend("Postgres")

    def test_check_storage_backend_rejects_other(self) -> None:
        """Anything other than 'postgres' should fail."""
        mod = self._import_module()
        assert not mod.check_storage_backend("sqlite")
        assert not mod.check_storage_backend("mysql")
        assert not mod.check_storage_backend("")

    def test_check_worker_queue_accepts_true(self) -> None:
        """'true' should pass."""
        mod = self._import_module()
        assert mod.check_worker_queue("true")
        assert mod.check_worker_queue("TRUE")
        assert mod.check_worker_queue("1")
        assert mod.check_worker_queue("yes")

    def test_check_worker_queue_rejects_false(self) -> None:
        """'false' or other values should fail."""
        mod = self._import_module()
        assert not mod.check_worker_queue("false")
        assert not mod.check_worker_queue("0")
        assert not mod.check_worker_queue("no")
        assert not mod.check_worker_queue("")

    def test_check_database_url_accepts_postgresql(self) -> None:
        """postgresql:// URLs should pass."""
        mod = self._import_module()
        assert mod.check_database_url("postgresql://user:strong-password-123@localhost:5432/db")
        assert mod.check_database_url("postgres://user:strong-password-123@postgres:5432/db")

    def test_check_database_url_rejects_non_postgres(self) -> None:
        """Non-postgres URLs should fail."""
        mod = self._import_module()
        assert not mod.check_database_url("sqlite:///path/to/db")
        assert not mod.check_database_url("mysql://user:pass@localhost/db")
        assert not mod.check_database_url("")
        assert not mod.check_database_url("not-a-url")

    def test_check_api_key_rejects_default_placeholders(self) -> None:
        """Known default API key values should fail."""
        mod = self._import_module()
        assert not mod.check_api_key("change-me"), "'change-me' should fail"
        assert not mod.check_api_key("change-me-to-a-random-secret"), "default placeholder should fail"
        assert not mod.check_api_key("dev-key"), "'dev-key' should fail"
        assert not mod.check_api_key("test-key"), "'test-key' should fail"
        assert not mod.check_api_key("your-api-key-here"), "placeholder should fail"
        assert not mod.check_api_key("CHANGE_ME_GENERATE_STRONG_API_KEY")
        assert not mod.check_api_key("replace_this_with_random_key")

    def test_check_api_key_rejects_short_keys(self) -> None:
        """API keys shorter than 16 chars should fail."""
        mod = self._import_module()
        assert not mod.check_api_key("short")
        assert not mod.check_api_key("123456789012345")

    def test_check_api_key_accepts_strong_key(self) -> None:
        """A strong, long API key should pass."""
        mod = self._import_module()
        assert mod.check_api_key("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")

    def test_check_db_password_rejects_default_placeholders(self) -> None:
        """Known default DB password values should fail."""
        mod = self._import_module()
        assert not mod.check_db_password("dataforge"), "'dataforge' default should fail"
        assert not mod.check_db_password("change-me"), "'change-me' should fail"
        assert not mod.check_db_password("change-me-to-a-strong-password"), "default placeholder should fail"
        assert not mod.check_db_password("password"), "'password' should fail"
        assert not mod.check_db_password("postgres"), "'postgres' should fail"
        assert not mod.check_db_password("CHANGE_ME_GENERATE_STRONG_DB_PASSWORD")
        assert not mod.check_db_password("replace_this_with_random_password")

    def test_check_database_url_rejects_placeholder_password_pattern(self) -> None:
        """Database URL password validation should reject generated placeholder text."""
        mod = self._import_module()
        assert not mod.check_database_url("postgresql://dataforge:CHANGE_ME_GENERATE_STRONG_DB_PASSWORD@localhost:5432/db")

    def test_check_grafana_password_rejects_placeholder_pattern(self) -> None:
        """Grafana password validation should reject generated placeholder text."""
        mod = self._import_module()
        assert not mod.check_grafana_password("CHANGE_ME_GENERATE_STRONG_GRAFANA_PASSWORD")

    def test_check_distinct_api_keys_rejects_reused_role_key(self) -> None:
        """Production role API keys must be separate secrets."""
        mod = self._import_module()
        env = {
            "DATAFORGE_API_KEY": "same-strong-key-value-123",
            "DATAFORGE_OPERATOR_API_KEY": "same-strong-key-value-123",
            "DATAFORGE_ADMIN_API_KEY": "different-strong-key-value-123",
        }
        assert not mod.check_distinct_api_keys(env)

    def test_check_distinct_api_keys_accepts_unique_role_keys(self) -> None:
        """Distinct production role API keys should pass the role separation check."""
        mod = self._import_module()
        env = {
            "DATAFORGE_API_KEY": "user-strong-key-value-123",
            "DATAFORGE_OPERATOR_API_KEY": "operator-strong-key-value-123",
            "DATAFORGE_ADMIN_API_KEY": "admin-strong-key-value-123",
        }
        assert mod.check_distinct_api_keys(env)

    def test_check_db_password_rejects_short_passwords(self) -> None:
        """Passwords shorter than 8 chars should fail."""
        mod = self._import_module()
        assert not mod.check_db_password("short")
        assert not mod.check_db_password("1234567")

    def test_check_db_password_accepts_strong_password(self) -> None:
        """A strong, unique password should pass."""
        mod = self._import_module()
        assert mod.check_db_password("secure-password-123!@#")

    def test_check_env_accepts_production(self) -> None:
        """'production' should pass."""
        mod = self._import_module()
        assert mod.check_env("production")
        assert mod.check_env("PRODUCTION")
        assert mod.check_env("Production")

    def test_check_env_rejects_non_production(self) -> None:
        """Anything other than 'production' should fail."""
        mod = self._import_module()
        assert not mod.check_env("development")
        assert not mod.check_env("test")
        assert not mod.check_env("staging")
        assert not mod.check_env("")


class TestCheckProdEnvIntegration:
    """Integration tests exercising the full main() flow."""

    def _import_module(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_prod_env",
            _SCRIPT_PATH / "check_prod_env.py",
        )
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    def test_valid_env_passes_all_checks(self, env_file) -> None:
        """A fully valid .env should pass all checks."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
                "DATAFORGE_DB_PASSWORD": "secure-password-123",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://dataforge:secure-password-123@postgres:5432/dataforge",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_QUEUE_BACKEND": "postgres",
                "DATAFORGE_METRICS_TOKEN": "metrics-token-a1b2c3d4e5f6a1b2",
                "DATAFORGE_ENV": "production",
                "GRAFANA_PASSWORD": "strong-grafana-password-123",
            },
        )

        env = mod.load_env_file(env_file)
        all_pass = True
        checks_list = [
            ("DATAFORGE_API_KEY", True, mod.check_api_key),
            ("DATAFORGE_CORS_ORIGINS", True, mod.check_cors_origins),
            ("DATAFORGE_DB_PASSWORD", True, mod.check_db_password),
            ("DATAFORGE_STORAGE_BACKEND", True, mod.check_storage_backend),
            ("DATAFORGE_DATABASE_URL", True, mod.check_database_url),
            ("DATAFORGE_WORKER_QUEUE", True, mod.check_worker_queue),
            ("DATAFORGE_QUEUE_BACKEND", True, mod.check_queue_backend),
            ("DATAFORGE_METRICS_TOKEN", True, lambda v: mod._check_api_key_not_default("DATAFORGE_METRICS_TOKEN", v)),
            ("DATAFORGE_ENV", True, None),
            ("GRAFANA_PASSWORD", True, mod.check_grafana_password),
        ]
        for name, required, validator in checks_list:
            passed = mod.check_var(env, name, required=required, validator=validator)
            if not passed:
                all_pass = False

        assert all_pass, "All production env checks should pass with valid values"

    def test_rejects_development_env(self, env_file) -> None:
        """Env with DATAFORGE_ENV=development should fail."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
                "DATAFORGE_DB_PASSWORD": "secure-password-123",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://user:pass@localhost/db",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_ENV": "development",
            },
        )

        env = mod.load_env_file(env_file)
        assert not mod.check_var(env, "DATAFORGE_ENV", required=True, validator=mod.check_env)

    def test_rejects_wildcard_cors(self, env_file) -> None:
        """Env with wildcard CORS should fail CORS check."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["*"]',
                "DATAFORGE_DB_PASSWORD": "secure-password-123",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://user:pass@localhost/db",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_ENV": "production",
            },
        )

        env = mod.load_env_file(env_file)
        assert not mod.check_var(env, "DATAFORGE_CORS_ORIGINS", required=True, validator=mod.check_cors_origins)

    def test_rejects_default_api_key(self, env_file) -> None:
        """Default/placeholder API key should fail."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "change-me-to-a-random-secret",
                "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
                "DATAFORGE_DB_PASSWORD": "secure-password-123",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://user:pass@localhost/db",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_ENV": "production",
            },
        )

        env = mod.load_env_file(env_file)
        # check_api_key should reject the default placeholder
        assert not mod.check_var(env, "DATAFORGE_API_KEY", required=True, validator=mod.check_api_key)

    def test_rejects_default_db_password(self, env_file) -> None:
        """Default DB password should fail with check_db_password."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["https://myapp.example.com"]',
                "DATAFORGE_DB_PASSWORD": "dataforge",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://user:pass@localhost/db",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_ENV": "production",
            },
        )

        env = mod.load_env_file(env_file)
        # check_db_password should reject the default 'dataforge' value
        assert not mod.check_var(env, "DATAFORGE_DB_PASSWORD", required=True, validator=mod.check_db_password)

    def test_accepts_postgres_env(self, env_file) -> None:
        """All valid Postgres env vars should pass."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["https://app.example.com", "https://dashboard.example.com"]',
                "DATAFORGE_DB_PASSWORD": "strong-password-xyz",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://dataforge:strong-password-xyz@postgres:5432/dataforge",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_QUEUE_BACKEND": "postgres",
                "DATAFORGE_METRICS_TOKEN": "metrics-token-strong-value-xyz",
                "DATAFORGE_ENV": "production",
                "GRAFANA_PASSWORD": "strong-grafana-password-xyz",
            },
        )

        env = mod.load_env_file(env_file)
        checks = [
            mod.check_var(env, "DATAFORGE_API_KEY", required=True, validator=mod.check_api_key),
            mod.check_var(env, "DATAFORGE_CORS_ORIGINS", required=True, validator=mod.check_cors_origins),
            mod.check_var(env, "DATAFORGE_DB_PASSWORD", required=True, validator=mod.check_db_password),
            mod.check_var(env, "DATAFORGE_STORAGE_BACKEND", required=True, validator=mod.check_storage_backend),
            mod.check_var(env, "DATAFORGE_DATABASE_URL", required=True, validator=mod.check_database_url),
            mod.check_var(env, "DATAFORGE_WORKER_QUEUE", required=True, validator=mod.check_worker_queue),
            mod.check_var(env, "DATAFORGE_QUEUE_BACKEND", required=True, validator=mod.check_queue_backend),
            mod.check_var(
                env,
                "DATAFORGE_METRICS_TOKEN",
                required=True,
                validator=lambda v: mod._check_api_key_not_default("DATAFORGE_METRICS_TOKEN", v),
            ),
            mod.check_var(env, "DATAFORGE_ENV", required=True, validator=mod.check_env),
            mod.check_var(env, "GRAFANA_PASSWORD", required=True, validator=mod.check_grafana_password),
        ]
        assert all(checks), f"All checks should pass: {checks}"

    def test_rejects_missing_grafana_password(self, env_file) -> None:
        """Missing GRAFANA_PASSWORD should fail validation."""
        mod = self._import_module()
        _write_env(
            env_file,
            {
                "DATAFORGE_API_KEY": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "DATAFORGE_CORS_ORIGINS": '["https://app.example.com"]',
                "DATAFORGE_DB_PASSWORD": "strong-password-xyz",
                "DATAFORGE_STORAGE_BACKEND": "postgres",
                "DATAFORGE_DATABASE_URL": "postgresql://dataforge:strong-password-xyz@postgres:5432/dataforge",
                "DATAFORGE_WORKER_QUEUE": "true",
                "DATAFORGE_ENV": "production",
                # GRAFANA_PASSWORD is deliberately missing
            },
        )

        env = mod.load_env_file(env_file)
        assert not mod.check_var(env, "GRAFANA_PASSWORD", required=True, validator=mod.check_grafana_password)
