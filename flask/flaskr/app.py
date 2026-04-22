import os
from flask import Flask, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from auth import auth_bp
from blog import blog_bp
from sensor_data import sensor_bp
from camera import camera_bp
from admin import admin_bp
from db import cleanup_old_logs


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )
    app.extensions['limiter'] = limiter

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(blog_bp, url_prefix='/blog')
    app.register_blueprint(sensor_bp, url_prefix='/api/blog')
    app.register_blueprint(camera_bp, url_prefix='/api/camera')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'"
        )
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains'
            )
        return response

    @app.route('/')
    def home():
        return redirect(url_for('auth.api_login'))

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(cleanup_old_logs, 'interval', hours=1)
    scheduler.start()

    return app


app = create_app()


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug)
