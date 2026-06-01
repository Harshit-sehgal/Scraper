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

DB_BACKEND="${DATAFORGE_STORAGE_BACKEND:-sqlite}"
if [ "${DB_BACKEND}" != "postgres" ]; then
    echo "[ERROR] DATAFORGE_STORAGE_BACKEND is set to '${DB_BACKEND}'. Restore is only supported for Postgres storage."
    exit 1
fi

DB_USER="dataforge"
DB_NAME="dataforge"
CONTAINER_NAME="dataforge-postgres"

echo "[WARNING] This action will OVERWRITE active database tables in '${DB_NAME}'."
read -p "Are you absolutely sure you want to proceed with restore? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore aborted."
    exit 0
fi

echo "[INFO] Restoring database backup from '${BACKUP_FILE}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[WARNING] Container '${CONTAINER_NAME}' is not running. Attempting local restore."
    if ! command -v psql &> /dev/null; then
        echo "[ERROR] psql utility not found locally, and container is not running."
        exit 1
    fi
    # Local restore
    gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${DATAFORGE_DB_PASSWORD:-}" psql -h localhost -U "${DB_USER}" -d "${DB_NAME}"
else
    # Restore inside running docker container
    gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}"
fi

echo "[SUCCESS] Postgres restore completed successfully."
echo "======================================================================"
