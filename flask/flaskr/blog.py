import logging
from datetime import datetime, timedelta

from flask import Blueprint, render_template, jsonify

from .db import LocalSession, EventLogs
from .decorators import login_required

logger = logging.getLogger(__name__)
blog_bp = Blueprint('blog', __name__)


def format_timestamp(timestamp_value):
    """Safely format timestamp value to HH:MM:SS string"""
    if timestamp_value is None:
        return ""
    if isinstance(timestamp_value, datetime):
        return timestamp_value.strftime("%H:%M:%S")
    return str(timestamp_value)


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

        temperature_data = []
        for row in temp_logs:
            if row.timestamp is not None:
                timestamp_str = row.timestamp.strftime("%H:%M:%S")
            else:
                timestamp_str = ""
            temperature_data.append({
                "timestamp": timestamp_str,
                "value": row.value
            })
        
        motion_data = []
        for row in motion_logs:
            if row.timestamp is not None:
                timestamp_str = row.timestamp.strftime("%H:%M:%S")
            else:
                timestamp_str = ""
            motion_data.append({
                "timestamp": timestamp_str,
                "value": row.value
            })
        
        return jsonify({"temperature": temperature_data, "motion": motion_data})
    except Exception:
        logger.exception("get_sensor_data failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


