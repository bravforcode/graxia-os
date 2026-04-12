#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-}"
if [[ -z "${TARGET_HOST}" ]]; then
  echo "usage: $0 <user@host>"
  exit 1
fi

scp deploy/scripts/harden-vps.sh "${TARGET_HOST}:/tmp/harden-vps.sh"
ssh "${TARGET_HOST}" "sudo bash /tmp/harden-vps.sh"
ssh "${TARGET_HOST}" "mkdir -p /opt/personal-os"
rsync -az --delete . "${TARGET_HOST}:/opt/personal-os/"
ssh "${TARGET_HOST}" "cd /opt/personal-os && docker compose -f docker-compose.prod.yml up -d"
echo "DR rebuild bootstrap complete. Run restore_database.py and smoke_test.py next."
