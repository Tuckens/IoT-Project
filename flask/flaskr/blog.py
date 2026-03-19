from flask import Blueprint, render_template

blog_bp = Blueprint('blog', __name__)

# Cette route sera accessible via l'URL /blog/ (si le préfixe est /blog)


@blog_bp.route('/')
def index():
    # Flask cherchera dans templates/blog/index.html
    return render_template('blog/index.html')
