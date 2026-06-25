#!/usr/bin/env bash
# Load file-backed runtime secrets into the environment.
#
# Docker Compose mounts secrets at /run/secrets/*; the app reads ordinary
# DATAFORGE_* env vars. This bridge lets production containers keep
# secret values out of docker inspect while preserving the existing app
# configuration path.

_load_secret_file_env() {
    local env_name="$1"
    local default_path="$2"
    local file_env_name="${env_name}_FILE"
    local file_path="${!file_env_name-}"

    if [[ -z "$file_path" ]]; then
        file_path="$default_path"
    fi
    if [[ ! -f "$file_path" ]]; then
        return 0
    fi

    local value
    value="$(cat "$file_path")"
    if [[ -z "$value" ]]; then
        echo "ERROR: $file_env_name points to an empty secret file" >&2
        return 1
    fi
    export "$env_name=$value"
}

_load_file_backed_runtime_secrets() {
    _load_secret_file_env DATAFORGE_API_KEY /run/secrets/dataforge_api_key
    _load_secret_file_env DATAFORGE_OPERATOR_API_KEY /run/secrets/dataforge_operator_api_key
    _load_secret_file_env DATAFORGE_ADMIN_API_KEY /run/secrets/dataforge_admin_api_key
    _load_secret_file_env DATAFORGE_SESSION_SECRET /run/secrets/dataforge_session_secret
}
