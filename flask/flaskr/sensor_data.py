from flask import Blueprint, render_template, request, jsonify
from .db import log_sensor_data, record_camera_event, LocalSession, EventLogs
from datetime import datetime, timedelta
import random

blog_bp = Blueprint('blog', __name__)


@blog_bp.route('/')
def index():
    return render_template('blog/index.html')


@blog_bp.route('/config', methods=['GET'])
def get_config():
    """Return application configuration flags to the frontend."""
    return jsonify({
        "MOCK_SENSORS": current_app.config.get('MOCK_SENSORS', False),
        "MOCK_VIDEO": current_app.config.get('MOCK_VIDEO', False)
    })


@blog_bp.route('/sensor_data', methods=['GET'])
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


@blog_bp.route('/sensor_data', methods=['POST'])
def post_sensor_data():
    """Receive sensor data from an IoT device and store it."""
    data = request.get_json()

    event_type = data.get('event_type')
    description = data.get('description', '')
    value = data.get('value')

    if event_type is None or value is None:
        return jsonify({"error": "event_type and value are required"}), 400

    result = log_sensor_data(event_type, description, value)
    return jsonify(result), result.get("status", 200)


@blog_bp.route('/summary', methods=['GET'])
def sensor_summary():
    """Return a quick summary (current temp, 24h max, etc.)."""
    data = get_sensor_summary()
    return jsonify(data)


@blog_bp.route('/record', methods=['POST'])
def record():
    """Log a camera recording event."""
    data = request.get_json()
    filename = data.get('filename')

    if not filename:
        return jsonify({"error": "filename is required"}), 400

    result = record_camera_event(filename)
    return jsonify(result), result.get("status", 200)
