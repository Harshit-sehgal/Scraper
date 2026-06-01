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
CONTAINER_NAME="dataforge-postgres"

echo "[INFO] Extracting pg_dump from container '${CONTAINER_NAME}'..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[WARNING] Container '${CONTAINER_NAME}' is not running. Attempting local pg_dump."
    if ! command -v pg_dump &> /dev/null; then
        echo "[ERROR] pg_dump utility not found locally, and container is not running."
        exit 1
    fi
    PGPASSWORD="${DATAFORGE_DB_PASSWORD:-}" pg_dump -h localhost -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"
else
    # Run pg_dump inside running docker container
    docker exec -t "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" | gzip > "${BACKUP_FILE}"
fi

# Restrict permissions
chmod 600 "${BACKUP_FILE}"

echo "[SUCCESS] Postgres backup completed successfully."
echo "          Backup File: ${BACKUP_FILE}"
echo "          Size:        $(du -h "${BACKUP_FILE}" | cut -f1)"
echo "          Permissions: owner read/write only (chmod 600)"
echo "======================================================================"
