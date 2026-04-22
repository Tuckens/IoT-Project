#!/usr/bin/env bash
# Raspberry Pi hardening for the shared-Wi-Fi demo.
# Run once on the Pi: sudo bash deploy/harden-pi.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

echo "[1/7] Updating packages"
apt-get update
apt-get -y upgrade
apt-get -y install ufw fail2ban unattended-upgrades nginx python3-venv

echo "[2/7] Enabling unattended security upgrades"
dpkg-reconfigure -plow unattended-upgrades || true

echo "[3/7] Configuring UFW firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
# SSH — tighten to the LAN you expect to attend the demo from.
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (ESP ingest + HTTPS redirect)'
ufw allow 443/tcp comment 'HTTPS dashboard'
ufw --force enable
ufw status verbose

echo "[4/7] Hardening SSH"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
echo "  -> SSH password login disabled. Copy your public key with ssh-copy-id BEFORE logging out."

echo "[5/7] Enabling fail2ban"
systemctl enable --now fail2ban

echo "[6/7] Creating iotapp service user"
id -u iotapp >/dev/null 2>&1 || useradd --system --home /home/pi/IoT-Project --shell /usr/sbin/nologin iotapp

echo "[7/7] Self-signed TLS certificate for the dashboard"
mkdir -p /etc/nginx/certs
if [[ ! -f /etc/nginx/certs/iot-dashboard.crt ]]; then
  openssl req -x509 -nodes -days 730 -newkey rsa:2048 \
    -keyout /etc/nginx/certs/iot-dashboard.key \
    -out /etc/nginx/certs/iot-dashboard.crt \
    -subj "/CN=bpem.local"
  chmod 600 /etc/nginx/certs/iot-dashboard.key
fi

echo "Done. Remaining manual steps:"
echo "  * Copy deploy/nginx-iot.conf to /etc/nginx/sites-available/iot-dashboard"
echo "    then: ln -s ../sites-available/iot-dashboard /etc/nginx/sites-enabled/ && nginx -t && systemctl reload nginx"
echo "  * Copy deploy/iot-dashboard.service to /etc/systemd/system/, daemon-reload, enable --now."
echo "  * Fill /home/pi/IoT-Project/flask/flaskr/.env (SECRET_KEY, ESP_TOKEN, SESSION_COOKIE_SECURE=1)."
echo "  * Bootstrap admin: BOOTSTRAP_ADMIN_USERNAME=... BOOTSTRAP_ADMIN_PASSWORD=... python db.py bootstrap-admin"
