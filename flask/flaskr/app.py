from flask import Flask, redirect, url_for, render_template
from config import Config
from auth import auth_bp
from blog import blog_bp
from sensor_data import sensor_bp
from camera import camera_bp
from admin import admin_bp
import os
import sqlite3
from flask import request, jsonify

app = Flask(__name__)
app.config.from_object(Config)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'iot_demo.db')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                temperature REAL,
                motion INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()


app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(blog_bp, url_prefix='/blog')
app.register_blueprint(sensor_bp, url_prefix='/api/blog')
app.register_blueprint(camera_bp, url_prefix='/api/camera')
app.register_blueprint(admin_bp, url_prefix='/admin')


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        data = request.get_json()

        if data and data.get('token') == 'REDACTED-TOKEN':
            conn = sqlite3.connect('iot_demo.db')
            c = conn.cursor()
            c.execute('''
                INSERT INTO sensor_data (message_id, temperature, motion)
                VALUES (?, ?, ?)
            ''', (data.get('id'), data.get('temp'), data.get('pir')))
            conn.commit()
            conn.close()

            return jsonify({"status": "success", "message": "Data saved"}), 201

        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    user_agent = request.headers.get('User-Agent', '')
    if 'ESP8266' in user_agent:
        return jsonify({"command": "none"}), 200

    return redirect(url_for('auth.api_login'))


@app.route('/sensor_data', methods=['GET'])
def get_sensor_data():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT timestamp, temperature, motion FROM sensor_data ORDER BY timestamp DESC LIMIT 15").fetchall()
    conn.close()

    temperature_data = [{"timestamp": r['timestamp'][-8:],
                         "value": r['temperature']} for r in reversed(rows)]
    motion_data = [{"timestamp": r['timestamp'][-8:],
                    "value": r['motion']} for r in reversed(rows)]

    return jsonify({
        "temperature": temperature_data,
        "motion": motion_data
    })


if __name__ == '__main__':
    init_db()  # On prépare la DB avant de lancer le serveur
    app.run(host='0.0.0.0', port=5000, debug=True)
