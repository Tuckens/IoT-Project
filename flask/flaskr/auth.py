from flask import Blueprint, render_template
from flask import request,jsonify
from db import create_user


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET'])
def render_register_page():
    return render_template('auth/register.html')

@auth_bp.route('/register',methods=['POST'])
def api_register():
    data = request.get_json()
    
    username = data.get('username')
    password = data.get('password')
    
    result = create_user(username,password)
    
    if result["success"]:

        return jsonify({"message": result["message"]}), result["status"]
    else:
    
        return jsonify({"error": result["error"]}), result["status"]
    
    




