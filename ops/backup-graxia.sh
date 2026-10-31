#!/usr/bin/env bash
# Dump the graxia production database, verify the archive, and prune old dumps.
# Runs on the VPS host. Credentials come from the container env, never from this file.
set -euo pipefail

CONTAINER="${GRAXIA_DB_CONTAINER:-graxia_prod_postgres}"
BACKUP_DIR="${GRAXIA_BACKUP_DIR:-/var/backups/graxia}"
MIN_FREE_MB="${GRAXIA_BACKUP_MIN_FREE_MB:-2048}"
KEEP_DAYS="${GRAXIA_BACKUP_KEEP_DAYS:-14}"
KEEP_WEEKLY_DAYS="${GRAXIA_BACKUP_KEEP_WEEKLY_DAYS:-28}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

free_mb=$(df -Pm "$BACKUP_DIR" | awk 'NR==2 {print $4}')
if [ "$free_mb" -lt "$MIN_FREE_MB" ]; then
  log "ERROR not enough free disk: ${free_mb}MB free, need ${MIN_FREE_MB}MB"
  exit 1
fi

stamp=$(date -u +%Y%m%d-%H%M)
final="$BACKUP_DIR/graxia-$stamp.dump"
tmp="$final.partial"
trap 'rm -f "$tmp"' EXIT

log "dump start container=$CONTAINER"
docker exec -i "$CONTAINER" sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$tmp"
chmod 600 "$tmp"

if [ ! -s "$tmp" ]; then
  log "ERROR dump is empty"
  exit 1
fi

# pg_restore --list reads the archive table of contents without restoring anything.
if ! docker exec -i "$CONTAINER" pg_restore --list > /dev/null < "$tmp"; then
  log "ERROR pg_restore --list rejected archive"
  exit 1
fi

mv "$tmp" "$final"
trap - EXIT
log "dump ok file=$final bytes=$(stat -c %s "$final")"

# Keep daily dumps for KEEP_DAYS. Keep Sunday dumps for KEEP_WEEKLY_DAYS.
find "$BACKUP_DIR" -maxdepth 1 -name 'graxia-*.dump' -mtime +"$KEEP_DAYS" -print0 |
while IFS= read -r -d '' old; do
  dow=$(date -r "$old" +%u)
  age_days=$(( ( $(date +%s) - $(stat -c %Y "$old") ) / 86400 ))
  if [ "$dow" = "7" ] && [ "$age_days" -le "$KEEP_WEEKLY_DAYS" ]; then
    continue
  fi
  rm -f -- "$old"
  log "pruned $old"
done

find "$BACKUP_DIR" -maxdepth 1 -name 'graxia-*.dump' -mtime +"$KEEP_WEEKLY_DAYS" -print0 |
while IFS= read -r -d '' old; do
  rm -f -- "$old"
  log "pruned $old"
done
