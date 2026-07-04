#!/bin/bash
# Deploy Gold Bot to Linux VPS
set -e

echo "=== GOLD BOT VPS DEPLOYMENT ==="

# 1. Copy files
echo "Copying files..."
scp -r "graxia/packages/quant_os/gold_bot" root@27.254.134.59:/opt/goldbot/gold_bot/
scp "graxia/packages/quant_os/.env" root@27.254.134.59:/opt/goldbot/.env

# 2. Create systemd service
echo "Setting up systemd service..."
scp "graxia/packages/quant_os/gold_bot/deploy/goldbot.service" root@27.254.134.59:/etc/systemd/system/

# 3. Enable and start
echo "Starting bot..."
ssh root@27.254.134.59 "systemctl daemon-reload && systemctl enable goldbot && systemctl start goldbot"

# 4. Check status
sleep 3
ssh root@27.254.134.59 "systemctl status goldbot --no-pager"

echo "=== DEPLOYMENT COMPLETE ==="
