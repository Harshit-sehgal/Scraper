#!/usr/bin/env bash
# =============================================================================
# DataForge Postgres Backup Script
# =============================================================================
# Automatically dumps and compresses the active Postgres database.
# Restricts access to the backup file to owner read/write only.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Resolve BACKUP_DIR against the project root, not the CWD. The
# previous relative ``backups`` would land wherever the operator
# happened to invoke the script from, which broke cron jobs and
# CI tasks that ran from a different working directory.
BACKUP_DIR="${DATAFORGE_BACKUP_DIR:-${PROJECT_DIR}/backups}"
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
    # Use newline-delimited output (one VAR per line) so the consumer can
    # read it with `while IFS= read -r` instead of `eval`. The previous
    # `eval` approach was a shell-injection risk: a crafted password
    # could execute arbitrary commands at parse time.
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
        # Strip newlines and any shell-special characters from values
        # to make the assignment safe even for unusual passwords.
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
    PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" pg_dump "${PORT_ARG}" -h "${TARGET_HOST}" -U "${DB_USER}" -d "${DB_NAME}"
else
    # Run pg_dump inside running docker container
    PORT_ARG=""
    if [ -n "${DB_PORT}" ]; then
        PORT_ARG="-p ${DB_PORT}"
    fi
    docker exec -e PGPASSWORD="${DATAFORGE_DB_PASSWORD:-${DB_PASS:-}}" -t "${CONTAINER_NAME}" pg_dump "${PORT_ARG}" -U "${DB_USER}" -d "${DB_NAME}"
fi > "${BACKUP_FILE}.tmp"

# Lock down permissions on the temp file *before* validating it.
# A chmod 600 over a partially-written or corrupt gzip would
# otherwise mask the failure behind a readable-looking filename
# for an hour until someone noticed the gzip -t failed at the
# restore site. We also do a gzip -t round-trip on the temp file
# to make sure pg_dump actually produced a non-empty, valid
# stream — and only rename to the final BACKUP_FILE on success.
chmod 600 "${BACKUP_FILE}.tmp"
if ! gunzip -t "${BACKUP_FILE}.tmp"; then
    echo "[ERROR] Backup integrity check failed (gunzip -t). Removing partial file."
    rm -f "${BACKUP_FILE}.tmp"
    exit 1
fi
mv "${BACKUP_FILE}.tmp" "${BACKUP_FILE}"

echo "[SUCCESS] Postgres backup completed successfully."
echo "          Backup File: ${BACKUP_FILE}"
echo "          Size:        $(du -h "${BACKUP_FILE}" | cut -f1)"
echo "          Permissions: owner read/write only (chmod 600)"
echo "======================================================================"
