#!/usr/bin/env bash
# Build graxia-backend from one git commit on the VPS, roll out backend/celery/beat,
# and roll back to the previous compose files + image if health checks fail.
#
# Usage: deploy/vps/deploy.sh [git-ref]   (default HEAD; host from $GRAXIA_VPS)
set -euo pipefail

ref="${1:-HEAD}"
host="${GRAXIA_VPS:-opportunity-vps}"
cd "$(git rev-parse --show-toplevel)"
sha=$(git rev-parse --short=12 --verify "${ref}^{commit}")
[ -z "$(git status --porcelain --untracked-files=no -- backend deploy/vps)" ] ||
  { echo "backend/ or deploy/vps has uncommitted changes" >&2; exit 1; }

echo "deploy $sha to $host"
# Upload the source for this commit only (tracked files, nothing from the working tree).
git archive --format=tar "$sha" backend deploy/vps |
  ssh -o BatchMode=yes "$host" "cat > /tmp/graxia-deploy-$sha.tar"

# Remote part. No `set -e`: every step checks its own result so a failure after the
# compose files are swapped always reaches rollback.
ssh -o BatchMode=yes "$host" bash -s -- "$sha" <<'REMOTE'
set -uo pipefail
sha=$1
app=/opt/graxia-os
rel=$app/releases
src=$rel/$sha
tarball=/tmp/graxia-deploy-$sha.tar
min_free_kb=$((3 * 1024 * 1024))   # 3 GiB
health_timeout=360                 # seconds; celery checks every 60s

die() { echo "deploy: $*" >&2; rm -f "$tarball"; exit 1; }

# Same invocation the running containers were created with (compose labels):
# project graxia-production, working dir /opt/graxia-os, env file .env.production.
compose() {
  docker compose -p graxia-production --project-directory "$app" \
    --env-file "$app/.env.production" "$@" </dev/null   # stdin is this script
}
live() {
  compose -f "$app/docker-compose.yml" -f "$app/docker-compose.production.override.yml" "$@"
}
image_tag() { docker inspect -f '{{.Config.Image}}' "$1" 2>/dev/null | cut -d: -f2; }
state() {
  docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$1" 2>/dev/null || echo missing/missing
}

# --- preflight: nothing is changed if any of this fails ---
free_kb=$(df -Pk / | awk 'NR==2 {print $4}')
[ "${free_kb:-0}" -ge "$min_free_kb" ] || die "only $((free_kb / 1024)) MiB free on /, need 3 GiB"
cd "$app" || die "missing $app"
prev=$(image_tag graxia_prod_backend)
[ -n "$prev" ] || die "cannot read current backend image tag"
PRODUCTION_TAG=$(image_tag graxia_prod_frontend)
[ -n "$PRODUCTION_TAG" ] || die "cannot read current frontend image tag"
export PRODUCTION_TAG
echo "current backend tag: $prev, frontend tag: $PRODUCTION_TAG"

rm -rf "$src" && mkdir -p "$src" && tar -x -C "$src" -f "$tarball" || die "extract failed"
rm -f "$tarball"

echo "building graxia-backend:$sha"
docker build -q -t "graxia-backend:$sha" \
  --label "org.opencontainers.image.revision=$sha" "$src/backend" </dev/null ||
  die "build failed; nothing changed"

GRAXIA_BACKEND_TAG=$sha compose \
  -f "$src/deploy/vps/docker-compose.base.yml" \
  -f "$src/deploy/vps/docker-compose.production.override.yml" config --quiet ||
  die "new compose files do not validate; nothing changed"

# --- swap compose files; from here on every failure rolls back ---
cp docker-compose.yml docker-compose.yml.prev &&
  cp docker-compose.production.override.yml docker-compose.production.override.yml.prev ||
  die "cannot back up compose files; nothing changed"

rollback() {
  echo "deploy: $1; rolling back to $prev" >&2
  cp docker-compose.yml.prev docker-compose.yml
  cp docker-compose.production.override.yml.prev docker-compose.production.override.yml
  # The old override may hardcode the image; GRAXIA_BACKEND_TAG only matters if it reads it.
  GRAXIA_BACKEND_TAG=$prev live up -d --no-deps --no-build backend celery beat ||
    echo "deploy: ROLLBACK FAILED, fix by hand in $app" >&2
  exit 1
}

cp "$src/deploy/vps/docker-compose.base.yml" docker-compose.yml &&
  cp "$src/deploy/vps/docker-compose.production.override.yml" docker-compose.production.override.yml ||
  rollback "cannot install new compose files"

GRAXIA_BACKEND_TAG=$sha live up -d --no-deps --no-build backend celery beat ||
  rollback "compose up failed"

# --- health gate: backend and celery healthy, beat running ---
deadline=$((SECONDS + health_timeout))
while :; do
  b=$(state graxia_prod_backend); c=$(state graxia_prod_celery); t=$(state graxia_prod_beat)
  echo "backend=$b celery=$c beat=$t"
  [ "$b" = running/healthy ] && [ "$c" = running/healthy ] && [ "${t%%/*}" = running ] && break
  case "$b $c $t" in
    *unhealthy*|*exited*|*dead*|*missing*) rollback "unhealthy: backend=$b celery=$c beat=$t" ;;
  esac
  [ "$SECONDS" -lt "$deadline" ] || rollback "not healthy after ${health_timeout}s"
  sleep 10
done

echo "$sha" > DEPLOYED_SHA
# Keep the 3 newest release dirs and their images.
ls -1dt "$rel"/*/ | tail -n +4 | while read -r old; do
  old=${old%/}
  docker image rm "graxia-backend:${old##*/}" >/dev/null 2>&1 || true
  rm -rf "$old"
done
echo "deployed $sha (previous $prev)"
REMOTE
