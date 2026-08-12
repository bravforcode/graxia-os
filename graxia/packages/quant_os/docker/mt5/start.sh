#!/bin/bash
# start.sh — Launch Xvfb virtual display for Wine MT5
set -e

echo "[INIT] Starting Xvfb virtual display..."

# Clean up any stale lock files
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

Xvfb :99 -screen 0 1280x720x24 -ac -nolisten tcp &
XVFB_PID=$!
sleep 2

if kill -0 $XVFB_PID 2>/dev/null; then
    echo "[INIT] Xvfb running (PID=$XVFB_PID)"
else
    echo "[INIT] ERROR: Xvfb failed to start"
    exit 1
fi

# Record health heartbeat
date +%s > /tmp/mt5-health

# Execute the CMD
exec "$@"
