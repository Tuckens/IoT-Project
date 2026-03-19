from flask import Flask, redirect, url_for


def create_app():
    app = Flask(__name__)
    
    # Load configuration
    from .config import Config
    app.config.from_object(Config)

    from . import auth
    from . import routes
    app.register_blueprint(auth.auth_bp, url_prefix='/api/auth')
    app.register_blueprint(routes.blog_bp, url_prefix='/api/blog')

    @app.route('/')
    def accueil():
        # Redirige automatiquement vers l'URL de connexion
        return redirect('/api/auth/login')

    return app
