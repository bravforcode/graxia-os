#!/bin/bash
# sync_to_vps.sh — Sync Graxia Trading files from local to VPS
# Run from quant_os directory on your local machine
set -euo pipefail

VPS="root@27.254.134.59"
VPS_DEST="/opt/graxia-trading"

echo "=========================================="
echo " Syncing Graxia Trading to VPS"
echo "=========================================="
echo "Source: $(pwd)"
echo "Dest:   $VPS:$VPS_DEST"
echo ""

# Step 1: Create dirs
echo "[1/5] Creating directories on VPS..."
ssh "$VPS" "mkdir -p $VPS_DEST/{data/{postgres,models,features,logs,sqlite},docker/{db,trainer,api},scripts,backups}"

# Step 2: Copy Docker files
echo "[2/5] Copying Docker config files..."
scp docker-compose.yml "$VPS:$VPS_DEST/"
scp docker/.env.example "$VPS:$VPS_DEST/.env.example"
scp docker/Dockerfile.api "$VPS:$VPS_DEST/docker/"
scp docker/Dockerfile.trainer "$VPS:$VPS_DEST/docker/"
scp docker/requirements.api.txt "$VPS:$VPS_DEST/docker/"
scp docker/requirements.trainer.txt "$VPS:$VPS_DEST/docker/"
scp docker/db/init.sql "$VPS:$VPS_DEST/docker/db/"
scp docker/trainer/crontab "$VPS:$VPS_DEST/docker/trainer/"
scp docker/trainer/entrypoint-trainer.sh "$VPS:$VPS_DEST/docker/trainer/"
scp scripts/deploy_vps.sh "$VPS:$VPS_DEST/scripts/"

# Step 3: Copy quant_os source
echo "[3/5] Copying quant_os source code (this may take a minute)..."
rsync -avz --delete --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
    --exclude='*.pyc' --exclude='.mypy_cache' --exclude='.pytest_cache' \
    --exclude='.ruff_cache' --exclude='__pycache__' --exclude='.ipynb_checkpoints' \
    --exclude='node_modules' --exclude='*.egg-info' \
    ./ "$VPS:$VPS_DEST/quant_os/"

# Step 4: Set permissions
echo "[4/5] Setting permissions..."
ssh "$VPS" "chmod +x $VPS_DEST/docker/trainer/entrypoint-trainer.sh $VPS_DEST/scripts/deploy_vps.sh"

# Step 5: Verify
echo "[5/5] Verifying..."
ssh "$VPS" "echo '=== Files on VPS ===' && find $VPS_DEST -type f | head -30 && echo '...' && find $VPS_DEST -type f | wc -l && echo 'total files'"

echo ""
echo "=========================================="
echo " Sync complete!"
echo "=========================================="
echo ""
echo "Next step: SSH to VPS and run:"
echo "  cd /opt/graxia-trading && bash scripts/deploy_vps.sh"
echo ""
