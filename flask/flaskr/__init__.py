from flask import Flask, redirect, url_for


def create_app():
    app = Flask(__name__)

    # Add a config.py which define DataBase Url
    # app.config.from_pyfile('../config.py')

    from . import auth
    from . import routes
    app.register_blueprint(auth.auth_bp, url_prefix='/api/auth')
    app.register_blueprint(routes.blog_bp, url_prefix='/api/blog')

    @app.route('/')
    def accueil():
        # Redirige automatiquement vers l'URL de connexion
        return redirect('/api/auth/login')

    return app
