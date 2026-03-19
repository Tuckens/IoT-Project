from flask import Flask, redirect, url_for, render_template
from auth import auth_bp

app = Flask(__name__)

app.register_blueprint(auth_bp, url_prefix='/auth')


@app.route('/')
def index():
    return redirect(url_for('auth.login'))


if __name__ == '__main__':
    app.run(debug=True)
