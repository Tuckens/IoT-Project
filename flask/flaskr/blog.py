import logging
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, jsonify

from db import log_sensor_data, record_camera_event, LocalSession, EventLogs
from decorators import login_required

logger = logging.getLogger(__name__)
blog_bp = Blueprint('blog', __name__)


@blog_bp.route('/')
@login_required
def index():
    return render_template('blog/index.html')


@blog_bp.route('/sensor_data', methods=['GET'])
@login_required
def get_sensor_data():
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


@blog_bp.route('/sensor_data', methods=['POST'])
@login_required
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


@blog_bp.route('/record', methods=['POST'])
@login_required
def record():
    data = request.get_json(silent=True) or {}
    filename = data.get('filename')
    if not filename or not isinstance(filename, str):
        return jsonify({"error": "filename is required"}), 400

    result = record_camera_event(filename)
    return jsonify(result), result.get("status", 200)
