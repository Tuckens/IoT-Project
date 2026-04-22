import logging
import random
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, current_app

from db import log_sensor_data, record_camera_event, LocalSession, EventLogs

logger = logging.getLogger(__name__)
sensor_bp = Blueprint('sensor', __name__)

# DHT22 published operating range: -40..80 °C. We allow a small margin.
TEMP_MIN_C = -40.0
TEMP_MAX_C = 85.0


def _limiter():
    return current_app.extensions.get('limiter')


@sensor_bp.route('/')
def index():
    return render_template('blog/index.html')


@sensor_bp.route('/config', methods=['GET'])
def get_config():
    return jsonify({
        "MOCK_SENSORS": current_app.config.get('MOCK_SENSORS', False),
        "MOCK_VIDEO": current_app.config.get('MOCK_VIDEO', False),
    })


@sensor_bp.route('/sensor_data', methods=['GET'])
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
            {"timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp else "",
             "value": log.value}
            for log in temp_logs
        ]
        motion_data = [
            {"timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp else "",
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
            "temperature": last_temp.value if last_temp else None,
            "motion": int(last_motion.value) if last_motion else None,
        })
    except Exception:
        logger.exception("get_latest failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


@sensor_bp.route('/sensor_data', methods=['POST'])
def post_sensor_data():
    data = request.get_json(silent=True) or {}

    event_type = data.get('event_type')
    description = str(data.get('description', ''))[:200]
    value = data.get('value')

    if event_type is None or value is None:
        return jsonify({"error": "event_type and value are required"}), 400
    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({"error": "value must be numeric"}), 400

    result = log_sensor_data(event_type, description, value)
    return jsonify(result), result.get("status", 200)


@sensor_bp.route('/sensor', methods=['POST'])
def receive_esp_data():
    """Endpoint de collecte pour l'ESP32.

    NOTE (pédagogique) : cette route accepte un token partagé passé en clair
    dans le JSON, par-dessus du HTTP. C'est la faille intentionnelle du projet
    — un attaquant sur le même Wi-Fi peut capturer le token et injecter des
    données. Tout le reste est malgré tout validé (bornes, types, taille).
    """
    # Limit the damage an attacker can do once they have the token.
    limiter = _limiter()
    if limiter is not None:
        limiter.limit("60 per minute")(lambda: None)()

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON body or invalid JSON"}), 400

    expected_token = current_app.config.get('ESP_TOKEN')
    if not expected_token or data.get('token') != expected_token:
        return jsonify({"error": "Invalid token"}), 403

    # --- Strict validation ---
    try:
        msg_id = int(data.get('id', 0))
    except (TypeError, ValueError):
        return jsonify({"error": "id must be an integer"}), 400

    temp_raw = data.get('temp')
    pir_raw = data.get('pir')
    if temp_raw is None or pir_raw is None:
        return jsonify({"error": "temp and pir fields are required"}), 400

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
    result_temp = log_sensor_data("temperature", desc, temp)
    result_pir = log_sensor_data("motion", desc, float(pir))

    if result_temp["success"] and result_pir["success"]:
        return jsonify({"success": True, "message": "Data logged"}), 200

    logger.warning("partial ESP log failure temp=%s pir=%s", result_temp, result_pir)
    return jsonify({"success": False, "error": "Internal error"}), 500


@sensor_bp.route('/record', methods=['POST'])
def record():
    data = request.get_json(silent=True) or {}
    filename = data.get('filename')
    if not filename or not isinstance(filename, str):
        return jsonify({"error": "filename is required"}), 400

    result = record_camera_event(filename)
    return jsonify(result), result.get("status", 200)
