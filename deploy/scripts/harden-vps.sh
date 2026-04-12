#!/usr/bin/env bash
set -euo pipefail

echo "[1/8] Update base packages"
apt-get update -y
apt-get upgrade -y
apt-get install -y ufw fail2ban unattended-upgrades auditd iptables-persistent

echo "[2/8] Harden SSH"
cat >/etc/ssh/sshd_config.d/personal-os-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
AllowTcpForwarding no
X11Forwarding no
AllowAgentForwarding no
PermitEmptyPasswords no
EOF
systemctl restart ssh || systemctl restart sshd

echo "[3/8] Configure UFW"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "[4/8] Configure DOCKER-USER chain"
iptables -N DOCKER-USER 2>/dev/null || true
iptables -C DOCKER-USER -i eth0 -p tcp --dport 5432 -j DROP 2>/dev/null || iptables -I DOCKER-USER -i eth0 -p tcp --dport 5432 -j DROP
iptables -C DOCKER-USER -i eth0 -p tcp --dport 6379 -j DROP 2>/dev/null || iptables -I DOCKER-USER -i eth0 -p tcp --dport 6379 -j DROP
iptables -C DOCKER-USER -i eth0 -p tcp --dport 5555 -j DROP 2>/dev/null || iptables -I DOCKER-USER -i eth0 -p tcp --dport 5555 -j DROP
iptables -C DOCKER-USER -i eth0 -p tcp --dport 8000 -j DROP 2>/dev/null || iptables -I DOCKER-USER -i eth0 -p tcp --dport 8000 -j DROP
netfilter-persistent save

echo "[5/8] Sysctl hardening"
cat >/etc/sysctl.d/99-personal-os-hardening.conf <<'EOF'
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.tcp_syncookies = 1
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
EOF
sysctl --system

echo "[6/8] Configure fail2ban"
cat >/etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 24h
EOF
systemctl enable fail2ban
systemctl restart fail2ban

echo "[7/8] Enable unattended upgrades"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "[8/8] Audit sensitive files"
auditctl -w /etc/passwd -p wa -k identity
auditctl -w /etc/shadow -p wa -k identity
auditctl -w /etc/sudoers -p wa -k privileged

echo "VPS hardening complete."
