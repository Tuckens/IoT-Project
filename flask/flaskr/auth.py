from flask import (
    Blueprint, render_template, request, jsonify, session,
    redirect, url_for, current_app
)

from .db import create_user, login, delete_user
from .decorators import admin_required

auth_bp = Blueprint('auth', __name__)


def _limiter():
    return current_app.extensions.get('limiter')


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

    limiter = _limiter()
    if limiter is not None:
        # 5 accounts per minute per IP — defeats trivial flooding and
        # username-enumeration via timing on a shared Wi-Fi.
        limiter.limit("5 per minute")(lambda: None)()

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
@admin_required
def api_delete():
    if request.method == 'GET':
        return render_template('auth/delete.html')

    # admin_required already verified the caller is still an Admin in the DB
    # (not just in the cookie). Identity of the requester still comes from
    # the session — never from the body — to stop requester-spoofing.
    requester_username: str = session.get('username') or ''
    if not requester_username:
        return jsonify({"error": "Not authenticated"}), 401

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


@auth_bp.route('/me', methods=['GET'])
def api_me():
    """Return the current user's identity + role, or 401 if not logged in.

    The dashboard uses this to decide whether to render the Admin link.
    We read through admin_required's DB re-fetch indirectly by hitting the
    session, which admin_required has already refreshed on any prior admin
    request — fine here because a stale 'Admin' flag only hides the link,
    it does not grant access.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "username": session.get('username'),
        "is_admin": session.get('permissions') == 'Admin',
    })


@auth_bp.route('/logout', methods=['POST'])
def api_logout():
    # POST only — a GET logout is trivially CSRFable via <img src=...>,
    # letting any page on the LAN log a user out.
    session.clear()
    return redirect(url_for('auth.api_login'))
