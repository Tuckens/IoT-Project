from flask import Flask, redirect, url_for


def create_app():
    app = Flask(__name__)

    # Add a config.py which define DataBase Url
    # app.config.from_pyfile('../config.py')

    from .auth import auth_bp

    app.register_blueprint(auth_bp)

    # --- LA NOUVELLE ROUTE ---

    @app.route('/')
    def index():
        # On redirige l'utilisateur vers la fonction 'login' du blueprint 'auth'
        return redirect(url_for('auth.login'))

    return app
