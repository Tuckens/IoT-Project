from flask import (
    Blueprint, render_template, request, jsonify, session,
    redirect, url_for, current_app
)

from db import create_user, login, delete_user

auth_bp = Blueprint('auth', __name__)


def _limiter():
    return current_app.extensions.get('limiter')


@auth_bp.route('/index', methods=['GET'])
def index():
    return render_template('auth/index.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def api_login():
    if request.method == "GET":
        return render_template('auth/login.html')

    limiter = _limiter()
    if limiter is not None:
        # 5 attempts per minute per IP — defence against brute force on the shared Wi-Fi.
        limiter.limit("5 per minute")(lambda: None)()

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    result = login(username, password)
    if result["success"]:
        session.clear()
        session['user_id'] = result['user_id']
        session['username'] = result['username']
        session['permissions'] = result['permissions']
        session.permanent = True
        return jsonify({"message": result["message"]}), result["status"]

    return jsonify({"error": result["error"]}), result["status"]


@auth_bp.route('/register', methods=['GET', 'POST'])
def api_register():
    if request.method == 'GET':
        return render_template('auth/register.html')

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    min_len = current_app.config.get('PASSWORD_MIN_LENGTH', 8)
    if len(username) < 3 or len(username) > 64:
        return jsonify({"error": "username must be 3–64 characters"}), 400
    if len(password) < min_len:
        return jsonify({"error": f"password must be at least {min_len} characters"}), 400

    result = create_user(username, password)
    status = result["status"]
    if result["success"]:
        return jsonify({"message": result["message"]}), status
    return jsonify({"error": result["error"]}), status


@auth_bp.route('/delete', methods=['POST', 'GET'])
def api_delete():
    if request.method == 'GET':
        return render_template('auth/delete.html')

    # Identity of the requester MUST come from the session, never from the body —
    # otherwise any client could spoof "requester_user":"Admin" and delete anyone.
    requester_username = session.get('username')
    if not requester_username:
        return jsonify({"error": "Authentication required"}), 401
    if session.get('permissions') != 'Admin':
        return jsonify({"error": "Admin permission required"}), 403

    data = request.get_json(silent=True) or {}
    target_username = (data.get('target_user') or '').strip()
    if not target_username:
        return jsonify({"error": "target_user is required"}), 400

    if target_username == requester_username:
        return jsonify({"error": "You cannot delete your own account"}), 400

    result = delete_user(target_username, requester_username)
    status = result["status"]
    if result["success"]:
        return jsonify({"message": result["message"]}), status
    return jsonify({"error": result["error"]}), status


@auth_bp.route('/logout', methods=['POST', 'GET'])
def api_logout():
    session.clear()
    return redirect(url_for('auth.api_login'))
