#!/usr/bin/env bash
# =============================================================================
# DataForge Postgres Backup Script
# =============================================================================
# Automatically dumps and compresses the active Postgres database.
# Restricts access to the backup file to owner read/write only.
# =============================================================================

set -euo pipefail

BACKUP_DIR="backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"

echo "======================================================================"
echo "DataForge Automated Postgres Backup Utility"
echo "======================================================================"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# 1. Locate configuration
ENV_FILE=".env.production"
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

# Ensure storage is postgres
DB_BACKEND="${DATAFORGE_STORAGE_BACKEND:-sqlite}"
if [ "${DB_BACKEND}" != "postgres" ]; then
    echo "[ERROR] DATAFORGE_STORAGE_BACKEND is set to '${DB_BACKEND}'. Backups are only supported for Postgres storage."
    exit 1
fi

# 2. Perform Dump
DB_USER="dataforge"
DB_NAME="dataforge"
DB_HOST="postgres"
DB_PASS=""
DB_PORT=""

if [ -n "${DATAFORGE_DATABASE_URL:-}" ]; then
    echo "[INFO] Parsing database configuration from DATAFORGE_DATABASE_URL."
    # Run python to parse URL securely
    parsed_config=$(python3 -c '
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
    # Escape quotes for bash safety
    user_esc = user.replace("\"", "\\\"")
    name_esc = name.replace("\"", "\\\"")
    host_esc = host.replace("\"", "\\\"")
    pass_esc = password.replace("\"", "\\\"")
    print(f"DB_USER=\"{user_esc}\";DB_NAME=\"{name_esc}\";DB_HOST=\"{host_esc}\";DB_PASS=\"{pass_esc}\";DB_PORT=\"{port}\"")
except Exception:
    pass
' 2>/dev/null || true)
    if [ -n "${parsed_config}" ]; then
        eval "${parsed_config}"
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

echo "[INFO] Extracting pg_dump from container '${CONTAINER_NAME}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[WARNING] Container '${CONTAINER_NAME}' is not running. Attempting local pg_dump."
    if ! command -v pg_dump &> /dev/null; then
        echo "[ERROR] pg_dump utility not found locally, and container is not running."
        exit 1
    fi
    TARGET_HOST="${DB_HOST}"
    if [ "${TARGET_HOST}" = "postgres" ]; then
        TARGET_HOST="localhost"
    fi
    PORT_ARG=""
    if [ -n "${DB_PORT}" ]; then
        PORT_ARG="-p ${DB_PORT}"
    fi
    PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" pg_dump ${PORT_ARG} -h "${TARGET_HOST}" -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"
else
    # Run pg_dump inside running docker container
    PORT_ARG=""
    if [ -n "${DB_PORT}" ]; then
        PORT_ARG="-p ${DB_PORT}"
    fi
    docker exec -e PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" -t "${CONTAINER_NAME}" pg_dump ${PORT_ARG} -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"
fi

# Restrict permissions
chmod 600 "${BACKUP_FILE}"

echo "[SUCCESS] Postgres backup completed successfully."
echo "          Backup File: ${BACKUP_FILE}"
echo "          Size:        $(du -h "${BACKUP_FILE}" | cut -f1)"
echo "          Permissions: owner read/write only (chmod 600)"
echo "======================================================================"
