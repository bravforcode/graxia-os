#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-config/docker-compose.production.yml}"
APP_URL="${APP_URL:?APP_URL is required}"
HISTORY_FILE="${DEPLOY_HISTORY_FILE:-deploy/deploy_history.jsonl}"
ROLLBACK_INDEX="${ROLLBACK_INDEX:-1}"
ENV_FILE="${ENV_FILE:-.env.production}"

if [[ ! -f "$HISTORY_FILE" ]]; then
  echo "Deploy history not found: $HISTORY_FILE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file not found: $ENV_FILE" >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

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
commit = str(target.get("commit_sha", "")).strip()
if not commit or commit == "unknown":
    raise SystemExit("rollback target has no source-build commit")
print(f"export ROLLBACK_COMMIT={commit!r}")
PY
)"
eval "$rollback_env"

CURRENT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
TARGET_COMMIT="$(git rev-parse "${ROLLBACK_COMMIT}^{commit}" 2>/dev/null || true)"
if [[ -z "$CURRENT_COMMIT" || "$CURRENT_COMMIT" != "$TARGET_COMMIT" ]]; then
  echo "Rollback source mismatch: checkout $ROLLBACK_COMMIT before running rollback." >&2
  exit 1
fi

compose config --quiet
compose up -d --wait postgres redis
compose build --pull backend frontend celery_worker celery_beat
compose up -d --remove-orphans --wait
compose exec -T backend curl -sf http://localhost:8000/health >/dev/null
python3 deploy/scripts/smoke_test.py --target "$APP_URL"

echo "Rollback complete: source-build=${ROLLBACK_COMMIT}"
