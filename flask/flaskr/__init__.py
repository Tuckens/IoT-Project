from flask import Flask, redirect, url_for, render_template


def create_app():
    app = Flask(__name__)

    # Load configuration
    from .config import Config
    app.config.from_object(Config)

    from . import auth
    from . import sensor_data
    app.register_blueprint(auth.auth_bp, url_prefix='/api/auth')
    # app.register_blueprint(sensor_data.blog_bp, url_prefix='/api/blog')

    return app


# --- AJOUTE CECI TOUT EN BAS ---
if __name__ == '__main__':
    # On crée l'application en appelant la fonction
    mon_app = create_app()

    # On lance le serveur en mode "debug" (pratique pour le développement)
    mon_app.run(debug=True, port=5000)
