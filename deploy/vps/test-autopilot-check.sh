#!/usr/bin/env bash
# Tests graxia-autopilot-check with fake docker, curl and psql on PATH. Run from the repo root.
set -u
dir=$(mktemp -d); trap 'rm -rf "$dir"' EXIT
mkdir -p "$dir/bin"
cat > "$dir/bin/docker" <<'EOF'
#!/usr/bin/env bash
[ "$1" = inspect ] && { echo "${FAKE_HEALTH:-healthy}"; exit 0; }
exit 1
EOF
cat > "$dir/bin/curl" <<'EOF'
#!/usr/bin/env bash
cat > "$CURL_CFG"
echo sent >> "$CURL_LOG"
exit "${FAKE_CURL_RC:-0}"
EOF
cat > "$dir/bin/psql-fake" <<'EOF'
#!/usr/bin/env bash
[ "${FAKE_PSQL_RC:-0}" = 0 ] || { echo "connection refused" >&2; exit "$FAKE_PSQL_RC"; }
echo "$FAKE_ROW"
EOF
chmod +x "$dir/bin/"*
printf 'TELEGRAM_BOT_TOKEN="t"\nTELEGRAM_CHAT_ID=1\n' > "$dir/env"
run() {
  FAKE_ROW="$1" CURL_LOG="$dir/curl.log" CURL_CFG="$dir/curl.cfg" PATH="$dir/bin:$PATH" \
    GRAXIA_ENV_FILE="$dir/env" GRAXIA_STATE_DIR="$dir/state" \
    GRAXIA_PSQL=psql-fake GRAXIA_DISK_MAX_PCT=101 bash deploy/vps/graxia-autopilot-check >/dev/null 2>&1
  echo $?
}
alerts() { if [ -f "$dir/curl.log" ]; then wc -l < "$dir/curl.log" | tr -d ' '; else echo 0; fi; }
fail() { echo "FAIL $1"; exit 1; }

[ "$(run '10|0')" = 0 ] || fail "healthy case"
[ "$(alerts)" = 0 ] || fail "healthy case must not alert"
[ "$(run '10|9')" = 2 ] || fail "failure-ratio case"
[ "$(run '0|0')" = 2 ] || fail "stalled case"
[ "$(alerts)" = 2 ] || fail "alert count"
grep -q 'bott/sendMessage' "$dir/curl.cfg" || fail "token quotes not stripped or url missing"
[ "$(FAKE_PSQL_RC=1 run '')" = 2 ] || fail "psql failure case"
[ "$(alerts)" = 3 ] || fail "psql failure must alert"
[ "$(run 'garbage')" = 2 ] || fail "unparseable psql output case"
[ "$(alerts)" = 4 ] || fail "unparseable output must alert"
[ "$(FAKE_HEALTH=unhealthy run '10|0')" = 2 ] || fail "unhealthy container case"
[ "$(alerts)" = 5 ] || fail "unhealthy container must alert"
# cooldown: the identical message is not re-sent within the cooldown, but the exit code stays 2
[ "$(FAKE_HEALTH=unhealthy run '10|0')" = 2 ] || fail "cooldown exit code"
[ "$(alerts)" = 5 ] || fail "cooldown must suppress identical alert"
# curl failure still exits 2 and is not recorded, so the next run retries
[ "$(FAKE_CURL_RC=7 run '10|10')" = 2 ] || fail "curl failure exit code"
[ "$(run '10|10')" = 2 ] || fail "retry after curl failure"
[ "$(alerts)" = 7 ] || fail "retry after curl failure must send"
echo PASS
