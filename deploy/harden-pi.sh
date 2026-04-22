#!/usr/bin/env bash
# Raspberry Pi hardening for the shared-Wi-Fi demo.
# Run once on the Pi: sudo bash deploy/harden-pi.sh
# Pass the login user (the account you SSH in with) as the first arg,
# or export APP_USER beforehand. Defaults to $SUDO_USER.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

APP_USER="${1:-${APP_USER:-${SUDO_USER:-}}}"
if [[ -z "${APP_USER}" ]]; then
  echo "Cannot determine the application user. Pass it explicitly:" >&2
  echo "  sudo APP_USER=boss bash deploy/harden-pi.sh" >&2
  exit 1
fi
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "User '${APP_USER}' does not exist." >&2
  exit 1
fi
echo "Hardening for user: ${APP_USER}"

echo "[1/8] Updating packages"
apt-get update
apt-get -y upgrade
apt-get -y install ufw fail2ban unattended-upgrades nginx python3-venv python3-pip

echo "[2/8] Enabling unattended security upgrades"
dpkg-reconfigure -plow unattended-upgrades || true

echo "[3/8] Configuring UFW firewall"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  comment 'SSH'
ufw allow 80/tcp  comment 'HTTP (ESP ingest + HTTPS redirect)'
ufw allow 443/tcp comment 'HTTPS dashboard'
ufw --force enable
ufw status verbose

echo "[4/8] Hardening SSH"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' /etc/ssh/sshd_config
sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config

# Restrict SSH to the app user — anyone else gets denied at the sshd layer.
if grep -q '^AllowUsers' /etc/ssh/sshd_config; then
  sed -i "s/^AllowUsers.*/AllowUsers ${APP_USER}/" /etc/ssh/sshd_config
else
  echo "AllowUsers ${APP_USER}" >> /etc/ssh/sshd_config
fi

sshd -t && systemctl restart ssh
echo "  -> SSH locked to '${APP_USER}' with key auth only."
echo "  -> Make sure ~${APP_USER}/.ssh/authorized_keys has your public key BEFORE closing this session."

echo "[5/8] Enabling fail2ban"
systemctl enable --now fail2ban

echo "[6/8] Kernel / sysctl hardening"
cat > /etc/sysctl.d/99-iot-hardening.conf <<'EOF'
# Ignore ICMP broadcasts (smurf defence)
net.ipv4.icmp_echo_ignore_broadcasts = 1
# Drop spoofed source-routed packets
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
# Reverse-path filtering (drop packets claiming to come from the wrong iface)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
# Log martian packets (forged source addresses)
net.ipv4.conf.all.log_martians = 1
# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
# SYN-flood protection
net.ipv4.tcp_syncookies = 1
EOF
sysctl -p /etc/sysctl.d/99-iot-hardening.conf

echo "[7/8] Self-signed TLS certificate for the dashboard"
mkdir -p /etc/nginx/certs
if [[ ! -f /etc/nginx/certs/iot-dashboard.crt ]]; then
  openssl req -x509 -nodes -days 730 -newkey rsa:2048 \
    -keyout /etc/nginx/certs/iot-dashboard.key \
    -out /etc/nginx/certs/iot-dashboard.crt \
    -subj "/CN=bpem.local"
  chmod 600 /etc/nginx/certs/iot-dashboard.key
fi

echo "[8/8] Journal size cap"
sed -i 's/^#\?SystemMaxUse=.*/SystemMaxUse=200M/' /etc/systemd/journald.conf
systemctl restart systemd-journald

echo ""
echo "Done. Remaining manual steps:"
echo "  * Copy deploy/nginx-iot.conf to /etc/nginx/sites-available/iot-dashboard"
echo "    then: ln -sf ../sites-available/iot-dashboard /etc/nginx/sites-enabled/"
echo "          rm -f /etc/nginx/sites-enabled/default && nginx -t && systemctl reload nginx"
echo "  * Substitute placeholders in the systemd unit and install it:"
echo "      sudo sed -e 's|__USER__|${APP_USER}|g' \\"
echo "               -e 's|__PROJECT_DIR__|/home/${APP_USER}/IoT-Project|g' \\"
echo "               deploy/iot-dashboard.service \\"
echo "          | sudo tee /etc/systemd/system/iot-dashboard.service > /dev/null"
echo "      sudo systemctl daemon-reload && sudo systemctl enable --now iot-dashboard"
echo "  * Fill /home/${APP_USER}/IoT-Project/flask/flaskr/.env (SECRET_KEY, ESP_TOKEN, SESSION_COOKIE_SECURE=1)."
echo "  * Bootstrap admin: BOOTSTRAP_ADMIN_USERNAME=... BOOTSTRAP_ADMIN_PASSWORD=... python db.py bootstrap-admin"
