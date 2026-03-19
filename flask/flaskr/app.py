from flask import Flask, redirect, url_for, render_template
from auth import auth_bp
from blog import blog_bp

app = Flask(__name__)

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(blog_bp, url_prefix='/blog')


@app.route('/')
def index():
    return redirect(url_for('auth.api_login'))


if __name__ == '__main__':
    app.run(debug=True)
