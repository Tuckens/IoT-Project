from flask import Flask


def create_app():
    app = Flask(__name__)

    # Add a config.py which define DataBase Url
    # app.config.from_pyfile('../config.py')

    from .main import main_bp

    app.register_blueprint(main_bp)

    return app
