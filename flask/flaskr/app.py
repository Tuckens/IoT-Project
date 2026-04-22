import os
from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from apscheduler.schedulers.background import BackgroundScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from config import Config
from auth import auth_bp
from blog import blog_bp
from sensor_data import sensor_bp
from camera import camera_bp
from admin import admin_bp
from db import cleanup_old_logs, cleanup_old_recordings


csrf = CSRFProtect()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Behind Nginx: trust a single proxy hop for scheme and client IP so that
    #   - session cookies can be flagged Secure based on the real scheme;
    #   - Flask-Limiter sees the real client IP instead of 127.0.0.1 (which
    #     would collapse everyone to the same bucket);
    #   - Flask-WTF's Referer check validates against the real origin.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    csrf.init_app(app)
    # Flask-WTF's init_app already setdefault()s WTF_CSRF_SSL_STRICT=True, so
    # a later setdefault is a no-op — we must assign directly. We keep the
    # Referer check ON (see Referrer-Policy below); this line just documents
    # that we rely on it rather than turning it off.
    app.config['WTF_CSRF_SSL_STRICT'] = True

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

    # The ESP32 ingest has no browser session; its auth is the shared token.
    # Requiring a CSRF token there would break the ESP firmware and miss the
    # point of the pedagogical flaw. Everything else still requires a token.
    csrf.exempt(app.view_functions['sensor.receive_esp_data'])

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        # same-origin: strip Referer for cross-site navigations (no leaking
        # our URLs to third parties) but keep it for our own POSTs, which
        # Flask-WTF's CSRF layer needs to validate.
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'"
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
    scheduler.add_job(cleanup_old_recordings, 'interval', hours=1)
    scheduler.start()

    return app


app = create_app()


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug)
