#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/quant_os"
SERVICE_USER="quant_os"
PYTHON="python3.11"

echo "[1/6] System dependencies"
apt-get update -y
apt-get install -y python3.11-venv python3.11-dev build-essential

echo "[2/6] Service user"
id -u "$SERVICE_USER" &>/dev/null || useradd --system --shell /usr/sbin/nologin "$SERVICE_USER"

echo "[3/6] Application directory"
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo "[4/6] Virtual environment + deps"
sudo -u "$SERVICE_USER" $PYTHON -m venv "$APP_DIR/.venv"
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[5/6] Environment file check"
if [ ! -f "$APP_DIR/.env" ]; then
    echo "WARNING: .env file missing at $APP_DIR/.env"
    echo "Copy .env.example to .env and fill in credentials before starting."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

echo "[6/6] Systemd + firewall"
cp "$APP_DIR/infra/systemd/quant_os.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable quant_os

ufw allow 22/tcp
ufw allow 8000/tcp
ufw --force enable

echo "Deploy complete. Start with: systemctl start quant_os"
