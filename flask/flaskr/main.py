from flask import Blueprint, request, jsonify
from db import log_sensor_data

main_bp = Blueprint('main',__name__)


@main_bp.route('/')
def index():
    return 'Hello Word !!'

@main_bp.route('/api/logs', methods=['POST'])
def receive_sensor_data():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    result = log_sensor_data(
        event_type=data.get('type'),
        description=data.get('desc'),
        val=data.get('value')
    )
    return jsonify(result), result["status"]