import os


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy flask/flaskr/.env.example to .env and fill it in."
        )
    return value


class Config:
    MOCK_SENSORS = False
    MOCK_VIDEO = False
    SENSOR_WINDOW_SECONDS = 60

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or "sqlite:///iot_demo.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = _required_env('SECRET_KEY')
    ESP_TOKEN = _required_env('ESP_TOKEN')

    # Session hardening — mitigates session hijacking over the shared Wi-Fi.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    PERMANENT_SESSION_LIFETIME = 60 * 60  # 1 hour

    # Password policy
    PASSWORD_MIN_LENGTH = 8
