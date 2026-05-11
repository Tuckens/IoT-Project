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
apt-get -y install ufw fail2ban unattended-upgrades nginx \
                   python3-venv python3-pip ffmpeg

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

echo "[7/9] Private CA + server cert for the dashboard"
mkdir -p /etc/nginx/certs
CA_CRT=/etc/nginx/certs/ca.crt
CA_KEY=/etc/nginx/certs/ca.key
SRV_CRT=/etc/nginx/certs/iot-dashboard.crt
SRV_KEY=/etc/nginx/certs/iot-dashboard.key

# Why: a plain self-signed cert gives a browser warning the admin learns to
# click through — and can't visually distinguish from an attacker's self-signed
# cert during an ARP-spoof MITM. Instead we generate a local CA, sign the
# server cert with it, and have the admin import the CA once on their laptop.
# After that, legitimate bpem.local is green-lock, anything else throws a
# hard error that cannot be bypassed without user action. The CA private key
# stays on the Pi at chmod 600 — never leaves it.

if [[ ! -f "${CA_CRT}" ]]; then
  openssl req -x509 -nodes -days 3650 -newkey rsa:4096 \
    -keyout "${CA_KEY}" -out "${CA_CRT}" \
    -subj "/CN=BPEM IoT Demo CA/O=BPEM/C=BE" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
  chmod 600 "${CA_KEY}"
  echo "  -> New CA generated at ${CA_CRT}"
  NEED_SERVER_CERT=1
fi

# Regenerate the server cert if it is missing OR not signed by our CA (e.g.
# the old standalone self-signed one from a previous deploy).
if [[ ! -f "${SRV_CRT}" ]] || ! openssl verify -CAfile "${CA_CRT}" "${SRV_CRT}" >/dev/null 2>&1; then
  NEED_SERVER_CERT=1
fi

if [[ "${NEED_SERVER_CERT:-0}" == "1" ]]; then
  CNF=$(mktemp)
  cat > "${CNF}" <<'EOF'
[req]
distinguished_name = req_distinguished_name
req_extensions     = v3_req
prompt             = no

[req_distinguished_name]
CN = bpem.local
O  = BPEM
C  = BE

[v3_req]
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names

[alt_names]
DNS.1 = bpem.local
DNS.2 = localhost
IP.1  = 127.0.0.1
EOF
  CSR=$(mktemp --suffix=.csr)
  openssl req -new -nodes -newkey rsa:2048 \
    -keyout "${SRV_KEY}" -out "${CSR}" -config "${CNF}"
  openssl x509 -req -in "${CSR}" \
    -CA "${CA_CRT}" -CAkey "${CA_KEY}" -CAcreateserial \
    -out "${SRV_CRT}" -days 730 \
    -extensions v3_req -extfile "${CNF}"
  rm -f "${CSR}" "${CNF}"
  chmod 600 "${SRV_KEY}"
  echo "  -> Server cert issued and signed by the CA."
fi

# Expose the CA cert to the app user so they can scp it to their laptop.
install -o "${APP_USER}" -g "${APP_USER}" -m 0644 \
  "${CA_CRT}" "/home/${APP_USER}/bpem-ca.crt"
echo "  -> CA copied to /home/${APP_USER}/bpem-ca.crt (ready to scp)."

echo "[8/10] Securing app secrets, database, and recordings dir perms"
# .env holds SECRET_KEY / ESP_TOKEN / DB URL — must not be world-readable.
# iot_demo.db holds pbkdf2 password hashes — same story.
APP_DIR="/home/${APP_USER}/IoT-Project/flask/flaskr"
if [[ -f "${APP_DIR}/.env" ]]; then
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi
if [[ -f "${APP_DIR}/iot_demo.db" ]]; then
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/iot_demo.db"
  chmod 600 "${APP_DIR}/iot_demo.db"
fi
# recordings/ holds video of the room — strictly admin-readable, never
# exposed by Nginx (it lives outside /static).
install -d -o "${APP_USER}" -g "${APP_USER}" -m 0700 "${APP_DIR}/recordings"

echo "[9/10] Journal size cap"
sed -i 's/^#\?SystemMaxUse=.*/SystemMaxUse=200M/' /etc/systemd/journald.conf
systemctl restart systemd-journald

echo "[10/10] Restart nginx if it was already loaded"
systemctl is-active --quiet nginx && systemctl reload nginx || true

echo ""
echo "Done. Remaining manual steps:"
echo "  * Import /home/${APP_USER}/bpem-ca.crt on every machine that will"
echo "    log in to the dashboard. See deploy/README.md § 'Trusting the CA'."
echo "    After import, https://bpem.local/ shows the green padlock."
echo "    An ARP-spoof MITM presenting a different cert will now fail with"
echo "    NET::ERR_CERT_AUTHORITY_INVALID and cannot be clicked through."
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
