#!/usr/bin/env bash
# =============================================================================
# DataForge Postgres Restore Script
# =============================================================================
# Automatically restores a compressed Postgres database backup.
# Restores into either a running Docker container or a local instance.
# =============================================================================

set -euo pipefail

echo "======================================================================"
echo "DataForge Postgres Restore Utility"
echo "======================================================================"

if [ "$#" -ne 1 ]; then
    echo "[ERROR] Missing backup file argument."
    echo "Usage:  $0 <path/to/backup_file.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "[ERROR] Backup file '${BACKUP_FILE}' does not exist on disk."
    exit 1
fi

# Load config
ENV_FILE="${PROJECT_DIR}/.env.production"
if [ -f "${ENV_FILE}" ]; then
    echo "[INFO] Loading configuration from '${ENV_FILE}'."
    # Export variables from file
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
elif [ -f ".env" ]; then
    echo "[INFO] Loading configuration from '.env'."
    set -a
    # shellcheck disable=SC1090
    source ".env"
    set +a
else
    echo "[INFO] Active environment variables will be used."
fi

DB_BACKEND="${DATAFORGE_STORAGE_BACKEND:-sqlite}"
if [ "${DB_BACKEND}" != "postgres" ]; then
    echo "[ERROR] DATAFORGE_STORAGE_BACKEND is set to '${DB_BACKEND}'. Restore is only supported for Postgres storage."
    exit 1
fi

DB_USER="dataforge"
DB_NAME="dataforge"
DB_HOST="postgres"
DB_PASS=""
DB_PORT=""

if [ -n "${DATAFORGE_DATABASE_URL:-}" ]; then
    echo "[INFO] Parsing database configuration from DATAFORGE_DATABASE_URL."
    # Use newline-delimited output to avoid shell injection from `eval`.
    parsed_config=$(DATAFORGE_DATABASE_URL="${DATAFORGE_DATABASE_URL:-}" python3 -c '
import os
from urllib.parse import urlsplit, unquote
url = os.environ.get("DATAFORGE_DATABASE_URL", "")
try:
    parsed = urlsplit(url)
    user = unquote(parsed.username) if parsed.username else "dataforge"
    name = parsed.path.lstrip("/") if parsed.path else "dataforge"
    host = parsed.hostname or "postgres"
    password = unquote(parsed.password) if parsed.password else ""
    port = parsed.port or ""
    for key, value in (("DB_USER", user), ("DB_NAME", name), ("DB_HOST", host), ("DB_PASS", password), ("DB_PORT", port)):
        safe = value.replace("\n", "").replace("\r", "")
        print(f"{key}={safe}")
except Exception:
    pass
' 2>/dev/null || true)
    if [ -n "${parsed_config}" ]; then
        while IFS= read -r line; do
            case "${line}" in
                DB_USER=*|DB_NAME=*|DB_HOST=*|DB_PASS=*|DB_PORT=*)
                    export "${line?}"
                    ;;
            esac
        done <<< "${parsed_config}"
    fi
fi

# Determine CONTAINER_NAME dynamically
CONTAINER_NAME="${DATAFORGE_CONTAINER_NAME:-${CONTAINER_NAME:-}}"
if [ -z "${CONTAINER_NAME}" ]; then
    if docker ps --format '{{.Names}}' | grep -q "^${DB_HOST}$"; then
        CONTAINER_NAME="${DB_HOST}"
    elif docker ps --format '{{.Names}}' | grep -q "^dataforge-${DB_HOST}$"; then
        CONTAINER_NAME="dataforge-${DB_HOST}"
    else
        CONTAINER_NAME="dataforge-postgres"
    fi
fi

echo "[WARNING] This action will OVERWRITE active database tables in '${DB_NAME}'."
# ``-t 30`` puts a 30-second upper bound on the prompt so a
# non-interactive shell (CI, cron, automation) doesn't hang
# forever. ``read -t 0`` returns immediately with non-zero when
# no input is available, which is the documented way to detect a
# non-TTY. We treat both timeouts and non-TTY as "no" to avoid
# accidentally restoring on a stray automated invocation.
if ! read -t 30 -p "Are you absolutely sure you want to proceed with restore? (y/N): " -n 1 -r; then
    REPLY=""
fi
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore aborted (no confirmation within 30s or non-TTY input)."
    exit 0
fi

echo "[INFO] Restoring database backup from '${BACKUP_FILE}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[WARNING] Container '${CONTAINER_NAME}' is not running. Attempting local restore."
    if ! command -v psql &> /dev/null; then
        echo "[ERROR] psql utility not found locally, and container is not running."
        exit 1
    fi
    TARGET_HOST="${DB_HOST}"
    if [ "${TARGET_HOST}" = "postgres" ]; then
        TARGET_HOST="localhost"
    fi
    PORT_ARG=()
    if [ -n "${DB_PORT}" ]; then
        PORT_ARG=(-p "${DB_PORT}")
    fi
    # Local restore
    gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" psql "${PORT_ARG[@]}" -h "${TARGET_HOST}" -U "${DB_USER}" -d "${DB_NAME}"
else
    # Restore inside running docker container
    PORT_ARG=()
    if [ -n "${DB_PORT}" ]; then
        PORT_ARG=(-p "${DB_PORT}")
    fi
    gunzip -c "${BACKUP_FILE}" | docker exec -e PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" -i "${CONTAINER_NAME}" psql "${PORT_ARG[@]}" -U "${DB_USER}" -d "${DB_NAME}"
fi

echo "[SUCCESS] Postgres restore completed successfully."
echo "======================================================================"
