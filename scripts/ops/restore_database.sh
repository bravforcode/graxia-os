#!/usr/bin/env bash
# Database Restore Script
# Restores the local PostgreSQL container from a compressed SQL backup.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"

if [[ "${1:-}" == "--yes" ]]; then
    AUTO_CONFIRM="yes"
    shift
else
    AUTO_CONFIRM="no"
fi

if [[ -z "${1:-}" ]]; then
    echo "Usage: ./restore_database.sh [--yes] <backup_file.sql.gz>"
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null || true
    exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Error: Backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-personal_os}"
POSTGRES_DB="${POSTGRES_DB:-personal_os}"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for restore operations" >&2
    exit 1
fi

if [[ "$AUTO_CONFIRM" != "yes" ]]; then
    echo "WARNING: This will overwrite the current database!"
    read -r -p "Are you sure you want to continue? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Restore cancelled"
        exit 0
    fi
fi

TEMP_SQL="$(mktemp)"
trap 'rm -f "$TEMP_SQL"' EXIT

echo "Stopping services..."
docker compose -f "$COMPOSE_FILE" down

echo "Starting PostgreSQL..."
docker compose -f "$COMPOSE_FILE" up -d postgres

echo "Waiting for PostgreSQL to be ready..."
for _ in {1..30}; do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo "Decompressing backup..."
gunzip -c "$BACKUP_FILE" > "$TEMP_SQL"

echo "Restoring database..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$TEMP_SQL"

echo "Starting all services..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Database restored successfully!"
echo "Run backend/scripts/smoke_tests.sh to verify the stack."
