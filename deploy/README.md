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
- Systemd runs the app as a dedicated `iotapp` user with `ProtectSystem=strict`.
- UFW allows only 22/80/443. SSH password auth disabled. Fail2ban on.
  Unattended security upgrades.

## One-time setup on the Pi

```bash
sudo bash deploy/harden-pi.sh

# Python env
python3 -m venv /home/pi/IoT-Project/.venv
/home/pi/IoT-Project/.venv/bin/pip install -r /home/pi/IoT-Project/requirements.txt
/home/pi/IoT-Project/.venv/bin/pip install gunicorn flask flask-limiter apscheduler sqlalchemy werkzeug

# Nginx site
sudo cp deploy/nginx-iot.conf /etc/nginx/sites-available/iot-dashboard
sudo ln -s ../sites-available/iot-dashboard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# App env
sudo -u iotapp cp flask/flaskr/.env.example flask/flaskr/.env
sudo -u iotapp nano flask/flaskr/.env    # fill SECRET_KEY, ESP_TOKEN, SESSION_COOKIE_SECURE=1

# Admin bootstrap
cd flask/flaskr
sudo -u iotapp env \
  BOOTSTRAP_ADMIN_USERNAME=admin \
  BOOTSTRAP_ADMIN_PASSWORD='choose-a-strong-one' \
  /home/pi/IoT-Project/.venv/bin/python db.py bootstrap-admin

# Service
sudo cp deploy/iot-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now iot-dashboard
sudo systemctl status iot-dashboard
```

## Wi-Fi caveats on the shared network
- Other attendees can sniff all plaintext traffic and ARP-spoof you. The
  dashboard (on HTTPS) is immune to passive sniffing but will trigger a
  self-signed-cert warning on first visit — this is expected.
- The ESP ingest stays on HTTP by design — that is the flaw you want
  discovered.
- Rotate `ESP_TOKEN` before the demo. It will be captured; rotating it
  afterwards stops replay attacks from video recordings of the event.
