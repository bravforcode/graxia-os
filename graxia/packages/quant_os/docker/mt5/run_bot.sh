#!/bin/bash
# run_bot.sh — Launch MT5 terminal + Python trading bot under Wine
set -e

WINE_PYTHON="$HOME/.wine/drive_c/Program Files/Python312/python.exe"
MT5_DIR="$HOME/.wine/drive_c/Program Files/MetaTrader 5"

echo "[BOT] ============================================"
echo "[BOT] Graxia MT5 Paper Trade Bot (Wine/Linux)"
echo "[BOT] ============================================"

# ── Step 1: Start MT5 terminal under Wine ────────────────────────────
echo "[BOT] Starting MT5 terminal..."
wine64 "$MT5_DIR/terminal64.exe" /portable /skipupdate /tester 2>/dev/null &
MT5_PID=$!
echo "[BOT] MT5 terminal PID=$MT5_PID"

# Wait for MT5 to initialize
echo "[BOT] Waiting for MT5 to initialize..."
for i in $(seq 1 30); do
    if wineserver -w 2>/dev/null; then
        break
    fi
    sleep 2
done

# ── Step 2: Run Python bot under Wine ────────────────────────────────
echo "[BOT] Starting Python trading bot..."
cd /app/quant_os

# Use Wine Python to run the bot (for MetaTrader5 package IPC)
wine "$WINE_PYTHON" -u scripts/paper_trade_bot.py 2>&1 &
BOT_PID=$!

echo "[BOT] Bot PID=$BOT_PID"
echo "[BOT] ============================================"
echo "[BOT] MT5 + Bot running. Ctrl+C to stop."
echo "[BOT] ============================================"

# Wait for either process to exit
wait -n $MT5_PID $BOT_PID 2>/dev/null
EXIT_CODE=$?

echo "[BOT] Process exited with code $EXIT_CODE"
echo "[BOT] Cleaning up..."

# Cleanup
kill $MT5_PID 2>/dev/null || true
kill $BOT_PID 2>/dev/null || true
wineserver -k 2>/dev/null || true

exit $EXIT_CODE
