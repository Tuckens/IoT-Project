from flask import Blueprint, render_template, request, jsonify, current_app
from db import log_sensor_data, record_camera_event, LocalSession, EventLogs
from datetime import datetime, timedelta
import random

sensor_bp = Blueprint('sensor', __name__)


@sensor_bp.route('/')
def index():
    return render_template('blog/index.html')


@sensor_bp.route('/config', methods=['GET'])
def get_config():
    """Return application configuration flags to the frontend."""
    return jsonify({
        "MOCK_SENSORS": current_app.config.get('MOCK_SENSORS', False),
        "MOCK_VIDEO": current_app.config.get('MOCK_VIDEO', False)
    })


@sensor_bp.route('/sensor_data', methods=['GET'])
def get_sensor_data():
    """Return the last 10 seconds of temperature and motion data as JSON."""
    if current_app.config.get('MOCK_SENSORS'):
        # Generate random mock data
        now = datetime.now()
        temperature_data = []
        motion_data = []
        for i in range(10):
            ts = (now - timedelta(seconds=10-i)).strftime("%H:%M:%S")
            temperature_data.append(
                {"timestamp": ts, "value": round(random.uniform(20.0, 25.0), 1)})
            motion_data.append(
                {"timestamp": ts, "value": random.choice([0, 1])})

        return jsonify({
            "temperature": temperature_data,
            "motion": motion_data
        })

    db = LocalSession()
    try:
        cutoff = datetime.now() - timedelta(seconds=10)

        temp_logs = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "temperature")
            .filter(EventLogs.timestamp >= cutoff)
            .order_by(EventLogs.timestamp.asc())
            .all()
        )

        motion_logs = (
            db.query(EventLogs)
            .filter(EventLogs.eventtype == "motion")
            .filter(EventLogs.timestamp >= cutoff)
            .order_by(EventLogs.timestamp.asc())
            .all()
        )

        temperature_data = [
            {
                "timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp else "",
                "value": log.value
            }
            for log in temp_logs
        ]

        motion_data = [
            {
                "timestamp": log.timestamp.strftime("%H:%M:%S") if log.timestamp else "",
                "value": log.value
            }
            for log in motion_logs
        ]

        return jsonify({
            "temperature": temperature_data,
            "motion": motion_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@sensor_bp.route('/sensor_data', methods=['POST'])
def post_sensor_data():
    """Receive sensor data from the dashboard/generic format."""
    data = request.get_json()

    event_type = data.get('event_type')
    description = data.get('description', '')
    value = data.get('value')

    if event_type is None or value is None:
        return jsonify({"error": "event_type and value are required"}), 400

    result = log_sensor_data(event_type, description, value)
    return jsonify(result), result.get("status", 200)


@sensor_bp.route('/sensor', methods=['POST'])
def receive_esp_data():
    """Receive sensor data from the ESP8266.

    Expected JSON payload from ESP:
        {"id": int, "temp": float, "pir": int, "user": str, "token": str}

    Creates two EventLogs rows per request: one for temperature, one for motion.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # --- Basic token validation ---
    expected_token = current_app.config.get('ESP_TOKEN', 'REDACTED-TOKEN')
    if data.get('token') != expected_token:
        return jsonify({"error": "Invalid token"}), 403

    temp = data.get('temp')
    pir = data.get('pir')
    msg_id = data.get('id', 0)

    if temp is None or pir is None:
        return jsonify({"error": "temp and pir fields are required"}), 400

    # Store temperature reading
    result_temp = log_sensor_data(
        event_type="temperature",
        description=f"ESP msg #{msg_id}",
        val=float(temp)
    )

    # Store motion reading
    result_pir = log_sensor_data(
        event_type="motion",
        description=f"ESP msg #{msg_id}",
        val=int(pir)
    )

    if result_temp["success"] and result_pir["success"]:
        return jsonify({"success": True, "message": "Data logged"}), 200
    else:
        errors = []
        if not result_temp["success"]:
            errors.append(f"temp: {result_temp.get('error')}")
        if not result_pir["success"]:
            errors.append(f"pir: {result_pir.get('error')}")
        return jsonify({"success": False, "errors": errors}), 400


@sensor_bp.route('/record', methods=['POST'])
def record():
    """Log a camera recording event."""
    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({"error": "filename is required"}), 400

    result = record_camera_event(filename)
    return jsonify(result), result.get("status", 200)
