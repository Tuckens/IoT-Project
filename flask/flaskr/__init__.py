from flask import Flask, redirect, url_for


def create_app():
    app = Flask(__name__)

    # Add a config.py which define DataBase Url
    # app.config.from_pyfile('../config.py')

    from . import auth
    app.register_blueprint(auth.auth_bp, url_prefix='/api/auth')

    return app
