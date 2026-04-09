from db import create_user, login, delete_user
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/index', methods=['GET'])
def index():
    return render_template('auth/index.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def api_login():
    if request.method == "GET":
        return render_template('auth/login.html')

    data = request.get_json()

    username = data.get('username')
    password = data.get('password')

    result = login(username, password)

    if result["success"]:
        session['user_id'] = result.get('user_id')
        session['username'] = result.get('username')
        session['permissions'] = result.get('permissions')
        return jsonify({"message": result["message"]}), result["status"]
    else:

        return jsonify({"error": result["error"]}), result["status"]


@auth_bp.route('/register', methods=['GET', 'POST'])
def api_register():

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


@auth_bp.route('/delete', methods=['POST', 'GET'])
def api_delete():
    if request.method == 'GET':
        return render_template('auth/delete.html')
    data = request.get_json()

    target_username = data.get("target_user")
    requester_username = data.get("requester_user")

    result = delete_user(target_username, requester_username)
    if result["success"]:

        return jsonify({"message": result["message"]}), result["status"]
    else:

        return jsonify({"error": result["error"]}), result["status"]


@auth_bp.route('/logout', methods=['GET'])
def api_logout():
    session.clear()
    return redirect(url_for('auth.api_login'))
