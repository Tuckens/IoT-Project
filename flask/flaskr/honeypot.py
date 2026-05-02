"""Legacy v1 API honeypot.

This blueprint serves a deliberately attractive but bogus "old version"
of the dashboard's API. It exists only to waste the time of attackers on
the shared Wi-Fi during the demo. None of these endpoints touch the real
database, the real authentication, or any sensor data.

The project's only real intentional flaw is the HMAC-signed but plaintext
ESP ingest at POST /api/blog/sensor (see sensor_data.py). Everything in
this file is decoy.

See HONEYPOT.md for the full design rationale and intended attacker journey.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import time

from flask import Blueprint, request, jsonify, Response

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

logger = logging.getLogger(__name__)

honeypot_bp = Blueprint('honeypot', __name__)


# ── Crypto material generated once per process. Restarting gunicorn
# rotates everything, which invalidates any tokens or ciphertexts that
# attackers may have captured during a previous round of the demo.
_HMAC_SECRET = secrets.token_bytes(32)
_KDF_SECRET = secrets.token_bytes(32)
_KDF_SALT = secrets.token_bytes(16)
_KDF_ITERATIONS = 1000


def _load_payload_bytes() -> bytes:
    """Read the punchline payload from disk, or fall back to plain text.

    Drop a GIF/PNG/JPG at flask/flaskr/honeypot_payload.gif to customise
    what the attacker sees once they have decrypted the chain. If no file
    is present the trap still works — the attacker just gets a text
    "gotcha" instead of a meme.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(here, 'honeypot_payload.gif')
    try:
        with open(candidate, 'rb') as f:
            return f.read()
    except OSError:
        return (
            b"Congratulations -- you spent ~30 minutes decrypting a meme.\n"
            b"The real bug is somewhere else entirely. Better luck next round.\n"
        )


_PAYLOAD_BYTES = _load_payload_bytes()


def _aes_cbc_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-CBC with PKCS#7 padding. Returns iv || ciphertext."""
    iv = secrets.token_bytes(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return iv + ct


_KDF_KEY = hashlib.pbkdf2_hmac(
    'sha256', _KDF_SECRET, _KDF_SALT, _KDF_ITERATIONS, dklen=32
)
_FLAG_ENCRYPTED = _aes_cbc_encrypt(_PAYLOAD_BYTES, _KDF_KEY)


# ── Fake user roster, generated once at boot. ~70 plausible-looking
# entries plus one buried 'flag_holder' that the puzzle points at.

def _make_fake_users() -> list:
    first_names = [
        "alice", "bob", "carol", "dan", "eve", "frank", "grace", "henry",
        "ivy", "jack", "kate", "leo", "mia", "noah", "olive", "pete",
        "quinn", "ruth", "sam", "tina", "ulysses", "vera", "walt", "xena",
        "yusuf", "zoe", "amy", "ben", "chris", "diana", "ed", "fiona",
        "george", "helen", "ian", "julia", "kevin", "lisa", "mark", "nina",
        "oscar", "paula", "quincy", "rita", "steve", "theo", "uma", "victor",
        "wanda", "xavier", "yvonne", "zach", "abe", "beth", "cindy", "derek",
        "elaine", "fred", "gina", "harry", "iris", "james", "karen", "luke",
        "monica", "nate", "ophelia", "paul",
    ]

    def _fake_hash() -> str:
        salt = base64.b64encode(secrets.token_bytes(16)).decode().rstrip('=')
        digest = secrets.token_hex(32)
        return f"pbkdf2:sha256:600000${salt}${digest}"

    rng = random.Random(0xBEEF)  # deterministic so timestamps stay stable across restarts

    users = []
    for i, name in enumerate(first_names, start=1):
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        hour = rng.randint(0, 23)
        minute = rng.randint(0, 59)
        users.append({
            "id": i,
            "username": name,
            "email": f"{name}@bpem.local",
            "password_hash": _fake_hash(),
            "role": "user",
            "last_login": f"2024-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00Z",
        })

    # flag_holder buried somewhere in the middle: page 4 of 7 with PAGE_SIZE=10.
    flag_user = {
        "id": 90,
        "username": "flag_holder",
        "email": "flag_holder@bpem.local",
        "password_hash": _fake_hash(),
        "role": "service",
        "last_login": "2024-01-15T03:42:18Z",
    }
    users.insert(34, flag_user)
    return users


_FAKE_USERS = _make_fake_users()
_PAGE_SIZE = 10


# ── Middleware: latency + flake. Both are common symptoms of a real
# legacy service that nobody wants to maintain anymore, so they reinforce
# the "forgotten v1 endpoint" framing rather than feeling like a trap.

@honeypot_bp.before_request
def _slow_and_flaky():
    # Random latency 800-1500 ms on every /api/v1/* request.
    time.sleep(random.uniform(0.8, 1.5))
    # ~1/15 requests fail with 503 to simulate an unstable backend.
    if random.randint(1, 15) == 1:
        return jsonify({
            "error": "Database connection lost, please retry",
            "status": "transient",
        }), 503


@honeypot_bp.after_request
def _legacy_headers(resp: Response) -> Response:
    resp.headers['X-API-Version'] = '1.4.2-deprecated'
    resp.headers['Deprecation'] = 'true'
    # RFC 8594: Sunset header advertises the date a resource will be
    # withdrawn. Realistic enough that any decent recon tool will note it.
    resp.headers['Sunset'] = 'Wed, 31 Dec 2024 23:59:59 GMT'
    resp.headers['Server'] = 'gunicorn/19.7.1'
    return resp


# ── Token format: <b64url header>.<b64url payload>.<b64url HMAC-SHA256>

_VALID_CREDS = {
    "admin": "admin2022",
    "demo": "demo",
    "mobile": "mobile2021",
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    s = s + '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _make_token(username: str, role: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode())
    p_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    msg = f"{h_b64}.{p_b64}".encode()
    sig = hmac.new(_HMAC_SECRET, msg, hashlib.sha256).digest()
    s_b64 = _b64url_encode(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"


def _verify_token(token: str):
    """Verify a v1 token. Buggy on purpose: an empty signature segment
    is accepted as if the token had been signed.

    Mirrors a real-world bug class: the developer wrote
        if sig and not hmac.compare_digest(...): return None
    forgetting that ``sig`` can be the empty string. The function then
    falls through and returns the payload unchecked. Forging an admin
    token therefore reduces to crafting any header / payload of choice
    and appending a trailing dot, e.g.

        eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4Iiwicm9sZSI6ImFkbWluIn0.
    """
    if not token:
        return None
    parts = token.split('.')
    if len(parts) != 3:
        return None
    h_b64, p_b64, s_b64 = parts
    try:
        payload = json.loads(_b64url_decode(p_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if s_b64:  # <-- the bug: empty signature is silently accepted
        msg = f"{h_b64}.{p_b64}".encode()
        expected = hmac.new(_HMAC_SECRET, msg, hashlib.sha256).digest()
        try:
            received = _b64url_decode(s_b64)
        except Exception:
            return None
        if not hmac.compare_digest(expected, received):
            return None
    return payload


def _require_admin():
    """Returns (payload, None) on success or (None, error_response) on failure."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None, (jsonify({"error": "missing or malformed Authorization header"}), 401)
    payload = _verify_token(auth[7:])
    if payload is None:
        return None, (jsonify({"error": "invalid token"}), 401)
    if payload.get('role') != 'admin':
        return None, (jsonify({"error": "admin role required"}), 403)
    return payload, None


# ── Endpoints ──────────────────────────────────────────────────────────

@honeypot_bp.route('/', methods=['GET'])
@honeypot_bp.route('', methods=['GET'])
def index():
    return jsonify({
        "service": "iot-dashboard-api",
        "version": "1.4.2-deprecated",
        "endpoints": {
            "POST /auth/login": "obtain bearer token",
            "GET /admin/users": "paginated user list (auth required)",
            "GET /admin/config": "service configuration (auth required)",
            "GET /admin/logs": "audit logs (auth required)",
            "GET /admin/export": "user export (auth required)",
        },
        "notice": "Use /api/ (v2) for new integrations. v1 retained for legacy mobile clients.",
    })


@honeypot_bp.route('/auth/login', methods=['POST'])
def login_endpoint():
    data = request.get_json(silent=True) or {}
    u = (data.get('username') or '').strip()
    p = data.get('password') or ''
    if _VALID_CREDS.get(u) == p:
        role = "admin" if u == "admin" else "user"
        return jsonify({
            "token": _make_token(u, role),
            "token_type": "Bearer",
            "expires_in": 3600,
            "role": role,
        })
    return jsonify({"error": "invalid credentials"}), 401


@honeypot_bp.route('/admin/users', methods=['GET'])
def admin_users():
    _, err = _require_admin()
    if err:
        return err

    # The "search" parameter looks helpful but always errors out — the
    # search index is "down". Forces the attacker to page through.
    if request.args.get('search'):
        return jsonify({
            "error": "search index unavailable",
            "hint": "use ?page=N pagination instead",
        }), 503

    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        page = 1
    page = max(1, page)
    start = (page - 1) * _PAGE_SIZE
    end = start + _PAGE_SIZE
    chunk = _FAKE_USERS[start:end]
    total = len(_FAKE_USERS)
    return jsonify({
        "page": page,
        "page_size": _PAGE_SIZE,
        "total": total,
        "total_pages": (total + _PAGE_SIZE - 1) // _PAGE_SIZE,
        "users": chunk,
    })


@honeypot_bp.route('/admin/config', methods=['GET'])
def admin_config():
    _, err = _require_admin()
    if err:
        return err
    return jsonify({
        "service": "iot-dashboard-api",
        "version": "1.4.2",
        "features": {
            "rate_limit": False,
            "cors": True,
            "audit_log": True,
        },
        "encryption": {
            "algorithm": "AES-256-CBC",
            "kdf": "PBKDF2-HMAC-SHA256",
            "kdf_salt_b64": base64.b64encode(_KDF_SALT).decode(),
            "kdf_iterations": _KDF_ITERATIONS,
            "encryption_user": "flag_holder",
            "flag_encrypted_b64": base64.b64encode(_FLAG_ENCRYPTED).decode(),
        },
        "deprecation_notice": "This API will be removed once the mobile app finishes migrating to v2.",
    })


@honeypot_bp.route('/admin/logs', methods=['GET'])
def admin_logs():
    _, err = _require_admin()
    if err:
        return err
    return jsonify({
        "logs": [
            {"ts": "2024-01-15T03:42:18Z", "user": "flag_holder", "event": "service_login", "ip": "127.0.0.1"},
            {"ts": "2024-01-15T03:42:19Z", "user": "flag_holder", "event": "secret_rotated", "ip": "127.0.0.1"},
            {"ts": "2024-01-15T03:42:20Z", "user": "flag_holder", "event": "config_blob_encrypted", "ip": "127.0.0.1"},
            {"ts": "2024-02-22T14:08:55Z", "user": "admin", "event": "config_export", "ip": "10.0.0.4"},
            {"ts": "2024-03-04T09:11:02Z", "user": "demo", "event": "login_failed", "ip": "10.0.0.7"},
            {"ts": "2024-03-04T09:11:30Z", "user": "demo", "event": "login_succeeded", "ip": "10.0.0.7"},
            {"ts": "2024-03-29T18:44:11Z", "user": "mobile", "event": "session_refresh", "ip": "10.0.0.91"},
            {"ts": "2024-04-12T07:02:48Z", "user": "admin", "event": "user_listing", "ip": "10.0.0.4"},
            {"ts": "2024-05-01T22:19:03Z", "user": "flag_holder", "event": "service_login", "ip": "127.0.0.1"},
            {"ts": "2024-06-18T11:36:27Z", "user": "admin", "event": "settings_updated", "ip": "10.0.0.4"},
        ],
        "truncated": True,
        "hint": "older entries archived to /var/log/iot-api/v1.archive (offline)",
    })


@honeypot_bp.route('/admin/export', methods=['GET'])
def admin_export():
    _, err = _require_admin()
    if err:
        return err
    user = (request.args.get('user') or '').strip()
    fmt = (request.args.get('format') or 'json').strip()
    if fmt != 'json':
        return jsonify({"error": "only format=json is implemented in v1"}), 400
    if not user:
        return jsonify({"error": "user query parameter is required"}), 400

    if user == 'flag_holder':
        return jsonify({
            "username": "flag_holder",
            "role": "service",
            "created_at": "2023-08-01T00:00:00Z",
            "kdf_secret_b64": base64.b64encode(_KDF_SECRET).decode(),
            "comment": "Service account used to seed PBKDF2 for at-rest config blobs.",
        })

    # For any other user, return a thin record so the endpoint feels
    # generic rather than tailored for flag_holder.
    return jsonify({
        "username": user,
        "role": "user",
        "created_at": "2023-08-01T00:00:00Z",
        "comment": "regular user export",
    })
