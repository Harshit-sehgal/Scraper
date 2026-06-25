"""Regression guards for production Docker secret wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
PROD_ENV_EXAMPLE = REPO_ROOT / ".env.production.example"
START_SERVER = REPO_ROOT / "scripts" / "start_server.sh"
START_WORKER = REPO_ROOT / "scripts" / "start_worker.sh"
SECRET_LOADER = REPO_ROOT / "scripts" / "load_runtime_secrets.sh"

FILE_BACKED_SECRETS = {
    "DATAFORGE_API_KEY": "dataforge_api_key",
    "DATAFORGE_OPERATOR_API_KEY": "dataforge_operator_api_key",
    "DATAFORGE_ADMIN_API_KEY": "dataforge_admin_api_key",
    "DATAFORGE_SESSION_SECRET": "dataforge_session_secret",
}


def _compose() -> dict[str, Any]:
    assert COMPOSE_FILE.is_file(), f"missing {COMPOSE_FILE}"
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def _environment_map(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment", {})
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    values: dict[str, str] = {}
    for item in env:
        key, _, value = str(item).partition("=")
        values[key] = value
    return values


def _service_secret_names(service: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in service.get("secrets", []) or []:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict):
            names.add(str(item.get("source", "")))
    return names


def test_prod_compose_mounts_api_and_session_secrets_for_app_and_worker() -> None:
    compose = _compose()
    top_level_secrets = compose.get("secrets", {})

    for secret_name in FILE_BACKED_SECRETS.values():
        assert secret_name in top_level_secrets
        assert top_level_secrets[secret_name]["file"] == f"./.secrets/{secret_name}"

    for service_name in ("dataforge", "worker"):
        service = compose["services"][service_name]
        env = _environment_map(service)
        mounted = _service_secret_names(service)
        for env_name, secret_name in FILE_BACKED_SECRETS.items():
            assert env[f"{env_name}_FILE"] == f"/run/secrets/{secret_name}"
            assert secret_name in mounted


def test_prod_env_example_uses_file_backed_api_and_session_secrets() -> None:
    text = PROD_ENV_EXAMPLE.read_text(encoding="utf-8")
    for env_name, secret_name in FILE_BACKED_SECRETS.items():
        assert f"{env_name}_FILE=./.secrets/{secret_name}" in text
        assert f"{env_name}=CHANGE_ME" not in text


def test_container_entrypoints_load_file_backed_runtime_secrets_before_validation() -> None:
    loader_text = SECRET_LOADER.read_text(encoding="utf-8")
    assert "_load_file_backed_runtime_secrets" in loader_text
    # The loader builds the ``<ENV>_FILE`` env-var name via string
    # concatenation rather than spelling out each literal. Check that
    # the dynamic construction is present and that each secret's
    # well-known default path is named explicitly — both are
    # necessary for the runtime to resolve a missing override.
    assert '"${env_name}_FILE"' in loader_text or "${env_name}_FILE" in loader_text
    for secret_name in FILE_BACKED_SECRETS.values():
        assert secret_name in loader_text
        assert f"/run/secrets/{secret_name}" in loader_text

    for script in (START_SERVER, START_WORKER):
        text = script.read_text(encoding="utf-8")
        assert "load_runtime_secrets.sh" in text
        assert "_load_file_backed_runtime_secrets" in text
        validator_call = '"$PYTHON_BIN" scripts/check_prod_env.py'
        assert text.index("_load_file_backed_runtime_secrets") < text.index(validator_call)
