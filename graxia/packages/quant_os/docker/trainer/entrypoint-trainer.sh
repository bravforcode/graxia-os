#!/bin/bash
set -e

echo "[$(date)] [INFO] graxia-trainer starting..."

# Fix log directory permissions (volume mount may be root-owned)
mkdir -p /logs /models /features
chmod -R 777 /logs 2>/dev/null || true

# Initial training if no model exists
if [ ! -f /models/latest_model.pkl ]; then
    echo "[$(date)] [INFO] No model found — initial training..."
    python /app/graxia/packages/quant_os/run_ml_train.py 2>&1 | tee -a /logs/initial-train.log || true
    echo "[$(date)] [INFO] Initial training complete (or skipped due to missing data)"
fi

# Start supercronic
echo "[$(date)] [INFO] Starting supercronic scheduler..."
exec supercronic -quiet /app/crontab
