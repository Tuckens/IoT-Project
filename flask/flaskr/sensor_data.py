import json
import logging
import random
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, current_app

from .db import log_sensor_data, record_camera_event, LocalSession, EventLogs
from .decorators import login_required

logger = logging.getLogger(__name__)
sensor_bp = Blueprint('sensor', __name__)

# DHT22 published operating range: -40..80 °C. We allow a small margin.
TEMP_MIN_C = -40.0
TEMP_MAX_C = 1000.0  # Increased for pedagogical flaw 


def _limiter():
    return current_app.extensions.get('limiter')


@sensor_bp.route('/')
@login_required
def index():
    return render_template('blog/index.html')


@sensor_bp.route('/config', methods=['GET'])
@login_required
def get_config():
    return jsonify({
        "MOCK_SENSORS": current_app.config.get('MOCK_SENSORS', False),
        "MOCK_VIDEO": current_app.config.get('MOCK_VIDEO', False),
    })


@sensor_bp.route('/sensor_data', methods=['GET'])
@login_required
def get_sensor_data():
    window = current_app.config.get('SENSOR_WINDOW_SECONDS', 60)
    try:
        limit = int(request.args.get('limit', window))
    except (ValueError, TypeError):
        limit = window
    limit = max(1, min(limit, 1000))

    if current_app.config.get('MOCK_SENSORS'):
        now = datetime.now()
        temperature_data, motion_data = [], []
        for i in range(limit):
            ts = (now - timedelta(seconds=limit - i)).strftime("%H:%M:%S")
            temperature_data.append({"timestamp": ts, "value": round(random.uniform(20.0, 25.0), 1)})
            motion_data.append({"timestamp": ts, "value": random.choice([0, 1])})
        return jsonify({"temperature": temperature_data, "motion": motion_data})

    db = LocalSession()
    try:
        cutoff = datetime.now() - timedelta(seconds=window)

        temp_logs = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "temperature")
            .filter(EventLogs.timestamp >= cutoff)
            .order_by(EventLogs.timestamp.asc())
            .limit(limit)
            .all()
        )
        motion_logs = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "motion")
            .filter(EventLogs.timestamp >= cutoff)
            .order_by(EventLogs.timestamp.asc())
            .limit(limit)
            .all()
        )

        temperature_data = [
            {"timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp is not None else "",
             "value": log.value}
            for log in temp_logs
        ]
        motion_data = [
            {"timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp is not None else "",
             "value": log.value}
            for log in motion_logs
        ]
        return jsonify({"temperature": temperature_data, "motion": motion_data})
    except Exception:
        logger.exception("get_sensor_data failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


@sensor_bp.route('/latest', methods=['GET'])
@login_required
def get_latest():
    if current_app.config.get('MOCK_SENSORS'):
        return jsonify({
            "temperature": round(random.uniform(20.0, 25.0), 1),
            "motion": random.choice([0, 1]),
        })

    db = LocalSession()
    try:
        last_temp = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "temperature")
            .order_by(EventLogs.timestamp.desc())
            .first()
        )
        last_motion = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "motion")
            .order_by(EventLogs.timestamp.desc())
            .first()
        )
        return jsonify({
            "temperature": last_temp.value if last_temp is not None else None,
            "motion": int(last_motion.value) if last_motion is not None else None,
        })
    except Exception:
        logger.exception("get_latest failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


@sensor_bp.route('/sensor', methods=['POST'])
def receive_esp_data():
    """ESP32 ingest endpoint.

    Pedagogical flaw (intentional, by design):
      - The channel is HTTP, not HTTPS.
      - Authentication is a shared secret included in the JSON body.
        This means a direct forgery without the secret is blocked, but
        a MITM attacker who can observe the ESP request can reuse the
        secret and modify temperature values in transit.
      - No replay protection (no timestamps/nonces).

    Anything else — strict payload validation, rate limiting, range
    bounds — stays in place so the blast radius of a successful attack
    is bounded to "false sensor readings + triggered recordings".
    """
    limiter = _limiter()
    if limiter is not None:
        limiter.limit("60 per minute")(lambda: None)()

    try:
        data = json.loads(request.get_data().decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return jsonify({"error": "Invalid JSON"}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    # --- Strict validation ---
    try:
        msg_id = int(data.get('id', 0))
    except (TypeError, ValueError):
        return jsonify({"error": "id must be an integer"}), 400

    temp_raw = data.get('temp')
    pir_raw = data.get('pir')
    secret = data.get('secret')
    if temp_raw is None or pir_raw is None or secret is None:
        return jsonify({"error": "temp, pir, and secret fields are required"}), 400

    expected_secret = current_app.config.get('ESP_SHARED_SECRET') or 'esp32_secret'
    if secret != expected_secret:
        return jsonify({"error": "Invalid secret"}), 403

    try:
        temp = float(temp_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "temp must be numeric"}), 400
    if not (TEMP_MIN_C <= temp <= TEMP_MAX_C):
        return jsonify({"error": "temp out of plausible range"}), 400

    try:
        pir = int(pir_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "pir must be an integer"}), 400
    if pir not in (0, 1):
        return jsonify({"error": "pir must be 0 or 1"}), 400

    desc = f"ESP msg #{msg_id}"
    result_temp = log_sensor_data(msg_id, "temperature", desc, temp)
    result_pir = log_sensor_data(msg_id, "motion", desc, float(pir))

    # Trigger recordings. Wrapped in try/except so a recording hiccup never
    # poisons the ingest path — data logging is the primary function.
    try:
        from .recording import recording_manager
        recording_manager.on_motion(pir == 1)
        recording_manager.on_temperature(temp)
    except Exception:
        logger.exception("recording trigger failed")

    if result_temp["success"] and result_pir["success"]:
        # Pedagogical flaw: Leak admin token only if temp is modified above 500 (requires MITM)
        response = {"success": True, "message": "Data logged"}
        if temp >= 500: 
            response["admin_token"] = "6258a39850da20b1"
        return jsonify(response), 200

    logger.warning("partial ESP log failure temp=%s pir=%s", result_temp, result_pir)
    return jsonify({"success": False, "error": "Internal error"}), 500


