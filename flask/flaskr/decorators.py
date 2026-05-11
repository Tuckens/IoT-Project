from functools import wraps
from flask import session, redirect, url_for, render_template, jsonify, request

from db import LocalSession, User


def _current_user():
    """Reload the session user from the database.

    We re-fetch on every protected request rather than trusting the permission
    string baked into the session cookie at login time. Otherwise demoting an
    admin in the database would not take effect until that admin's session
    expires, and a deleted account would keep its access.
    """
    user_id = session.get('user_id')
    if user_id is None:
        return None
    db = LocalSession()
    try:
        return db.query(User).filter(User.user_id == user_id).first()
    finally:
        db.close()


def _wants_json():
    return request.is_json or request.accept_mimetypes.best == 'application/json'


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = _current_user()
        if user is None:
            session.clear()
            if _wants_json():
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.api_login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = _current_user()
        if user is None:
            session.clear()
            if _wants_json():
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.api_login'))
        # Always mirror the DB permissions into the session so routes that
        # read session['permissions'] directly (defence-in-depth callers)
        # see the current value — not whatever was baked in at login.
        session['permissions'] = user.permissions
        if user.permissions != 'Admin':
            if _wants_json():
                return jsonify({"error": "Admin permission required"}), 403
            return render_template('auth/403.html'), 403
        return f(*args, **kwargs)
    return decorated_function
