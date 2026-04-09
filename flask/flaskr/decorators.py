from functools import wraps
from flask import session, redirect, url_for, render_template

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_id') is None:
            return redirect(url_for('auth.api_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_id') is None:
            return redirect(url_for('auth.api_login'))
        if session.get('permissions') != 'Admin':
            return render_template('auth/403.html'), 403
        return f(*args, **kwargs)
    return decorated_function
