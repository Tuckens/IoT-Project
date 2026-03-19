from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('iot_demo.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            temperature REAL,
            motion INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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

    return render_template('index.html')

@app.route('/api/sensor_data', methods=['GET'])
def get_sensor_data():
    conn = sqlite3.connect('iot_demo.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, temperature, motion FROM sensor_data ORDER BY timestamp DESC LIMIT 15")
    rows = c.fetchall()
    conn.close()

    temperature_data = [{"timestamp": r[0][-8:], "value": r[1]} for r in reversed(rows)]
    motion_data = [{"timestamp": r[0][-8:], "value": r[2]} for r in reversed(rows)]
    
    return jsonify({
        "temperature": temperature_data,
        "motion": motion_data
    })

if __name__ == '__main__':
    # Run locally on port 5000 (Nginx will proxy to this)
    app.run(host='0.0.0.0', port=5000)