# Deployment & Pi hardening

Threat model: Pi + ESP32 sit on a Wi-Fi network shared with other students who
are allowed to attack. **The only intentional flaw is the plaintext token sent
by the ESP32 to `POST /api/blog/sensor`.** Everything else must be hardened.

## What stays intentionally vulnerable
- `POST /api/blog/sensor` — served over plain HTTP, token in the JSON body.
  Documented in `esp-code/esp-code.ino` and `flask/flaskr/sensor_data.py`.

## Feature set

- **Regular users** log in and see only the live dashboard (camera stream,
  temperature/motion charts, latest values).
- **Admins** get an additional panel at `/admin/` with four tabs:
  - **Users** — rename, change role, change password (requires the admin's
    own password as confirmation), delete. The last remaining admin cannot
    be deleted or demoted.
  - **System Logs** — the 100 most recent `EventLogs` rows.
  - **Recordings** — list of camera clips with play (streaming with HTTP
    range support), download, and delete actions. A live indicator shows
    when a clip is currently being written.
  - **Settings** — temperature alarm threshold. Values clamped server-side
    to `[-20, 60] °C`.
- **Automatic recordings**: the ESP ingest endpoint
  `POST /api/blog/sensor` (the pedagogical-flaw route) triggers clips:
  - any `pir=1` starts a 5-second `motion` clip; repeated motion extends
    it;
  - any `temp < threshold` starts a `temperature` clip that keeps running
    until the reading recovers, with a hard 10-minute ceiling to protect
    the SD card.
  - Clips are stored under `flask/flaskr/recordings/` (outside `/static`,
    chmod `0700`, owned by the app user) as H.264-in-MP4 via
    `picamera2` + `ffmpeg`.
  - Only admin-authenticated requests can read or delete them. Filenames
    are server-generated and gated by a strict regex on every filesystem
    call — no path traversal possible.

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

## Trusting the CA (one-time, per laptop)

The hardening script now runs its own mini-CA. The server cert for
`bpem.local` is signed by that CA. If you import the CA cert on the
laptops that will log into the dashboard, you get a green padlock **and**
an ARP-spoofing attacker's forged cert causes a hard `NET::ERR_CERT_AUTHORITY_INVALID`
that cannot be clicked through — there is no "Continue anyway" button
once a site is backed by a trusted CA that the attacker does not control.

Grab the CA cert from the Pi first:

```bash
scp boss@bpem.local:/home/boss/bpem-ca.crt .
```

### Windows (Chrome / Edge / IE — anything using the Windows trust store)

```powershell
# Run in an elevated PowerShell
Import-Certificate -FilePath .\bpem-ca.crt `
    -CertStoreLocation Cert:\LocalMachine\Root
```
Or GUI: double-click `bpem-ca.crt` → *Install Certificate* → *Local
Machine* → *Place all certificates in the following store* → *Trusted
Root Certification Authorities*.

### Firefox (has its own trust store)
`about:preferences#privacy` → scroll to **Certificates** → *View
Certificates…* → *Authorities* tab → *Import…* → select
`bpem-ca.crt` → tick "Trust this CA to identify websites".

### macOS
```bash
sudo security add-trusted-cert -d -r trustRoot \
    -k /Library/Keychains/System.keychain bpem-ca.crt
```

### Linux (Debian/Ubuntu/Raspberry Pi OS family)
```bash
sudo cp bpem-ca.crt /usr/local/share/ca-certificates/bpem-ca.crt
sudo update-ca-certificates
```

### Android
Settings → Security → Encryption & credentials → Install a certificate
→ CA certificate → pick `bpem-ca.crt`.

After import, visit `https://bpem.local/` — the padlock is green. Close
and reopen the browser if the old warning sticks (cached). **Do not**
import the CA on attendee laptops that will attack you; they should see
the warning (that is the normal outside view).

## Wi-Fi caveats on the shared network
- Other attendees can sniff all plaintext traffic and ARP-spoof you.
  The dashboard (on HTTPS, trusted via the CA) is immune to both
  passive sniffing and active MITM.
- The ESP ingest stays on HTTP by design — that is the flaw you want
  discovered.
- Rotate `ESP_TOKEN` before the demo. It will be captured; rotating it
  afterwards stops replay attacks from video recordings of the event.
