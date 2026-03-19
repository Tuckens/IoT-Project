from .db import create_user, login
from flask import Blueprint, render_template
from flask import request, jsonify


auth_bp = Blueprint('auth', __name__)



@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == 'GET':
        return render_template('auth/register.html')

    data = request.get_json()

    username = data.get('username')
    password = data.get('password')

    result = create_user(username, password)
    if result["success"]:
        return jsonify({"message": result["message"]}), result["status"]
    else:
        return jsonify({"error": result["error"]}), result["status"]


@auth_bp.route('/login', methods=['POST','GET'])
def api_login():
    if request.method=='GET':
        return render_template('auth/login.html')
    data = request.get_json()

    username = data.get('username')
    password = data.get('password')

    result = login(username, password)

    if result["success"]:

        return jsonify({"message": result["message"]}), result["status"]
    else:

        return jsonify({"error": result["error"]}), result["status"]
