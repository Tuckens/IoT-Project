# Deployment & Pi hardening

Threat model: Pi + ESP32 sit on a Wi-Fi network shared with other students who
are allowed to attack. **The only intentional flaw is the plaintext token sent
by the ESP32 to `POST /api/blog/sensor`.** Everything else must be hardened.

## What stays intentionally vulnerable
- `POST /api/blog/sensor` — served over plain HTTP, token in the JSON body.
  Documented in `esp-code/esp-code.ino` and `flask/flaskr/sensor_data.py`.

## What is hardened
- Dashboard, admin panel, auth → behind Nginx + self-signed TLS on 443.
- HTTP → HTTPS redirect, except for the ESP ingest URL.
- Flask: no debug, session cookies `HttpOnly`+`SameSite=Lax` (+`Secure` once
  HTTPS is on), `SECRET_KEY`/`ESP_TOKEN` loaded from env, rate-limiting on
  login and on the ESP endpoint, strict payload validation, no exception
  strings returned to clients, security headers, admin routes guarded by
  session (never by body-supplied identity).
- Systemd runs the app under the project-owner user with `ProtectSystem=strict`
  and `ProtectHome=read-only`.
- UFW allows only 22/80/443. SSH password auth disabled. Fail2ban on.
  Unattended security upgrades.

## One-time setup on the Pi

The commands below assume you cloned the repo as user `boss` into
`/home/boss/IoT-Project`. Replace both values with yours — `whoami` and
`pwd` will tell you what to put.

```bash
# 0. Adjust these two to match your Pi
USER_NAME=$(whoami)
PROJECT_DIR=$HOME/IoT-Project

# 1. Firewall / SSH / nginx / user hardening
sudo bash $PROJECT_DIR/deploy/harden-pi.sh

# 2. Python venv + dependencies
python3 -m venv $PROJECT_DIR/.venv
$PROJECT_DIR/.venv/bin/pip install \
    flask flask-limiter sqlalchemy werkzeug apscheduler gunicorn

# 3. Nginx site
sudo cp $PROJECT_DIR/deploy/nginx-iot.conf /etc/nginx/sites-available/iot-dashboard
sudo ln -sf ../sites-available/iot-dashboard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 4. App env (SECRET_KEY, ESP_TOKEN, SESSION_COOKIE_SECURE=1)
cp $PROJECT_DIR/flask/flaskr/.env.example $PROJECT_DIR/flask/flaskr/.env
nano $PROJECT_DIR/flask/flaskr/.env

# 5. Bootstrap the admin user
cd $PROJECT_DIR/flask/flaskr
BOOTSTRAP_ADMIN_USERNAME=admin \
BOOTSTRAP_ADMIN_PASSWORD='choose-a-strong-one' \
$PROJECT_DIR/.venv/bin/python db.py bootstrap-admin

# 6. systemd service — substitute the placeholders before installing
sudo sed -e "s|__USER__|${USER_NAME}|g" \
         -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
         $PROJECT_DIR/deploy/iot-dashboard.service \
    | sudo tee /etc/systemd/system/iot-dashboard.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now iot-dashboard
sudo systemctl status iot-dashboard
```

If the service fails with `Result: resources`, the placeholders were not
substituted or the paths in `WorkingDirectory`, `EnvironmentFile` or
`ReadWritePaths` do not exist on disk. Check with:

```bash
sudo journalctl -xeu iot-dashboard -n 50 --no-pager
```

## Wi-Fi caveats on the shared network
- Other attendees can sniff all plaintext traffic and ARP-spoof you. The
  dashboard (on HTTPS) is immune to passive sniffing but will trigger a
  self-signed-cert warning on first visit — this is expected.
- The ESP ingest stays on HTTP by design — that is the flaw you want
  discovered.
- Rotate `ESP_TOKEN` before the demo. It will be captured; rotating it
  afterwards stops replay attacks from video recordings of the event.
