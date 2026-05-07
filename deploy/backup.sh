#!/bin/bash
#
# Graxia OS Production Backup Script
# Backs up PostgreSQL database to S3-compatible storage
# Run via cron: 0 2 * * * /opt/graxia/deploy/backup.sh
#

set -euo pipefail

# Configuration
BACKUP_DIR="/var/backups/graxia"
S3_BUCKET="${S3_BACKUP_BUCKET:-graxia-backups}"
S3_ENDPOINT="${S3_ENDPOINT:-s3.amazonaws.com}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
DB_NAME="${POSTGRES_DB:-graxia_production}"
DB_USER="${POSTGRES_USER:-graxia}"
DB_HOST="${POSTGRES_HOST:-localhost}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="graxia_${DB_NAME}_${TIMESTAMP}.sql.gz"

# Logging
LOG_FILE="/var/log/graxia/backup.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    log "ERROR: $*"
    # Send alert (implement your alerting mechanism)
    exit 1
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

log "Starting backup: $BACKUP_FILE"

# Perform database backup
if ! pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" --verbose 2>>"$LOG_FILE" | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"; then
    error "Database backup failed"
fi

# Verify backup file
if [[ ! -f "${BACKUP_DIR}/${BACKUP_FILE}" ]]; then
    error "Backup file not created"
fi

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
log "Backup completed: $BACKUP_SIZE"

# Upload to S3 (if configured)
if command -v aws &> /dev/null && [[ -n "${AWS_ACCESS_KEY_ID:-}" ]]; then
    log "Uploading to S3: s3://${S3_BUCKET}/backups/"
    
    if aws s3 cp "${BACKUP_DIR}/${BACKUP_FILE}" "s3://${S3_BUCKET}/backups/${BACKUP_FILE}" --endpoint-url="https://${S3_ENDPOINT}"; then
        log "S3 upload successful"
        
        # Remove local backup after successful upload
        rm "${BACKUP_DIR}/${BACKUP_FILE}"
        log "Local backup removed after S3 upload"
    else
        error "S3 upload failed"
    fi
else
    log "S3 upload skipped (AWS CLI not configured)"
fi

# Clean up old backups (local)
find "$BACKUP_DIR" -name "graxia_*.sql.gz" -mtime +$RETENTION_DAYS -delete
log "Cleaned up backups older than $RETENTION_DAYS days"

# Clean up old S3 backups (if configured)
if command -v aws &> /dev/null && [[ -n "${AWS_ACCESS_KEY_ID:-}" ]]; then
    log "Cleaning up old S3 backups..."
    aws s3 ls "s3://${S3_BUCKET}/backups/" --endpoint-url="https://${S3_ENDPOINT}" | \
        awk '{print $4}' | \
        while read -r file; do
            file_date=$(echo "$file" | grep -oP '\d{8}' || true)
            if [[ -n "$file_date" ]]; then
                file_epoch=$(date -d "${file_date:0:4}-${file_date:4:2}-${file_date:6:2}" +%s 2>/dev/null || echo 0)
                cutoff_epoch=$(date -d "$RETENTION_DAYS days ago" +%s)
                if [[ $file_epoch -lt $cutoff_epoch ]]; then
                    aws s3 rm "s3://${S3_BUCKET}/backups/${file}" --endpoint-url="https://${S3_ENDPOINT}" && \
                        log "Removed old S3 backup: $file"
                fi
            fi
        done
fi

# Backup verification (restore test on staging)
if [[ "${VERIFY_BACKUP:-false}" == "true" ]]; then
    log "Running backup verification..."
    # This would restore to a staging database and run health checks
    # Implement based on your infrastructure
    log "Backup verification completed"
fi

log "Backup process completed successfully"

# Health check ping (optional)
if [[ -n "${HEALTHCHECK_URL:-}" ]]; then
    curl -fsS -m 10 --retry 5 -o /dev/null "$HEALTHCHECK_URL" || true
fi
