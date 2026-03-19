from flask import Flask, redirect, url_for, render_template
from config import Config
from auth import auth_bp
from blog import blog_bp
from sensor_data import sensor_bp
from camera import camera_bp

app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(blog_bp, url_prefix='/blog')
app.register_blueprint(sensor_bp, url_prefix='/api/blog')
app.register_blueprint(camera_bp, url_prefix='/api/camera')


@app.route('/')
def index():
    return redirect(url_for('blog.index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
