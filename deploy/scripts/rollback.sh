#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
APP_URL="${APP_URL:?APP_URL is required}"
HISTORY_FILE="${DEPLOY_HISTORY_FILE:-deploy/deploy_history.jsonl}"
ROLLBACK_INDEX="${ROLLBACK_INDEX:-1}"

if [[ ! -f "$HISTORY_FILE" ]]; then
  echo "Deploy history not found: $HISTORY_FILE" >&2
  exit 1
fi

rollback_env="$(
  HISTORY_FILE="$HISTORY_FILE" ROLLBACK_INDEX="$ROLLBACK_INDEX" python3 - <<'PY'
import json
import os
from pathlib import Path

records = [
    json.loads(line)
    for line in Path(os.environ["HISTORY_FILE"]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
healthy = [r for r in records if r.get("smoke_test_result") == "pass"]
healthy = healthy[-3:]
index = int(os.environ["ROLLBACK_INDEX"])
if index >= len(healthy):
    raise SystemExit(f"rollback index {index} unavailable; healthy releases retained={len(healthy)}")
target = healthy[-1 - index]
print(f"export BACKEND_DIGEST={target['backend_digest']!r}")
print(f"export FRONTEND_DIGEST={target['frontend_digest']!r}")
print(f"export ROLLBACK_COMMIT={target.get('commit_sha', 'unknown')!r}")
PY
)"
eval "$rollback_env"

docker compose -f "$COMPOSE_FILE" pull backend frontend worker-critical worker-default worker-background beat
docker compose -f "$COMPOSE_FILE" up -d --no-deps backend
sleep 10
docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8000/health >/dev/null
docker compose -f "$COMPOSE_FILE" up -d --no-deps worker-critical worker-default worker-background beat frontend
python3 deploy/scripts/smoke_test.py --target "$APP_URL"

echo "Rollback complete: commit=${ROLLBACK_COMMIT} backend=${BACKEND_DIGEST} frontend=${FRONTEND_DIGEST}"
