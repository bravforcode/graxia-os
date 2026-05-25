#!/usr/bin/env bash
# Database Backup Script
# Backs up the local PostgreSQL container to local storage and optionally S3.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="backup_${DATE}.sql"
COMPRESSED_FILE="${BACKUP_FILE}.gz"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-personal_os}"
POSTGRES_DB="${POSTGRES_DB:-personal_os}"

mkdir -p "$BACKUP_DIR"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required for backups" >&2
    exit 1
fi

if ! docker compose -f "$COMPOSE_FILE" ps --status running postgres >/dev/null 2>&1; then
    echo "postgres service is not running; start the local stack before backing up" >&2
    exit 1
fi

echo "Starting database backup..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_DIR/$BACKUP_FILE"

gzip "$BACKUP_DIR/$BACKUP_FILE"

echo "Database backed up to: $BACKUP_DIR/$COMPRESSED_FILE"

if [[ -n "${AWS_S3_BUCKET:-}" ]]; then
    if command -v aws >/dev/null 2>&1; then
        echo "Uploading to S3..."
        aws s3 cp "$BACKUP_DIR/$COMPRESSED_FILE" "s3://${AWS_S3_BUCKET}/backups/"
        echo "Uploaded to S3"
    else
        echo "AWS_S3_BUCKET is set but aws CLI is unavailable; skipping upload" >&2
    fi
fi

find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +7 -delete

echo "Backup completed successfully!"
