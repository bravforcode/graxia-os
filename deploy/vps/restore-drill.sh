#!/usr/bin/env bash
# Restore a graxia production dump into a throwaway container and compare exact row counts with production.
# Production is only read (one read-only transaction counting rows). The drill container has no network.
# Usage: restore-drill.sh <graxia-production.dump>   (decrypted pg_dump -Fc archive, not the .age file)
set -euo pipefail
dump="${1:?usage: restore-drill.sh <graxia-production.dump>}"
PROD="${GRAXIA_PROD_CONTAINER:-graxia_prod_postgres}"
WAIT_S="${DRILL_WAIT_S:-120}"

[ -r "$dump" ] || { echo "cannot read $dump" >&2; exit 1; }
[ "$(head -c5 "$dump")" = PGDMP ] || { echo "$dump is not a pg_dump custom archive (still encrypted?)" >&2; exit 1; }
image="${DRILL_IMAGE:-$(docker inspect -f '{{.Config.Image}}' "$PROD")}"

name="graxia_restore_drill_$$"
work=$(mktemp -d)
cleanup() { docker stop "$name" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT

start=$(date +%s)
echo "starting $name from $image"
docker run -d --rm --network none --name "$name" -e POSTGRES_PASSWORD=drill -e PGPASSWORD=drill -e POSTGRES_DB=graxia "$image" >/dev/null

# The entrypoint runs initdb on a socket-only temporary server and then restarts; TCP on 127.0.0.1
# only answers once the final server is up.
deadline=$((start + WAIT_S))
until docker exec "$name" psql -h 127.0.0.1 -U postgres -d graxia -Atc 'select 1' >/dev/null 2>&1; do
  [ "$(date +%s)" -lt "$deadline" ] || { echo "drill postgres not ready after ${WAIT_S}s" >&2; docker logs "$name" 2>&1 | tail -20 >&2; exit 1; }
  sleep 1
done

echo "restoring $dump"
docker exec -i "$name" pg_restore -h 127.0.0.1 -U postgres -d graxia --no-owner --no-acl < "$dump"
restored=$(date +%s)

# One exact count(*) per public base table, emitted as "table|rows" in table order.
count_sql="select format('select %L || ''|'' || count(*) from public.%I', table_name, table_name)
  from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'
  order by table_name \gexec"
printf '%s\n' "$count_sql" | docker exec -i "$name" psql -h 127.0.0.1 -U postgres -d graxia -At -v ON_ERROR_STOP=1 > "$work/drill.counts"
printf 'set default_transaction_read_only = on;\n%s\n' "$count_sql" \
  | docker exec -i "$PROD" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -q -v ON_ERROR_STOP=1' > "$work/prod.counts"

echo "tables_restored=$(wc -l < "$work/drill.counts" | tr -d ' ')"
echo "rto_seconds=$((restored - start))"
if diff "$work/prod.counts" "$work/drill.counts"; then
  echo "row counts match"
else
  echo "row counts differ (< production, > restored); expected only for rows written after the dump"
fi
