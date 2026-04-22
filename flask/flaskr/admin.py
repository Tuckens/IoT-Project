import logging

from flask import Blueprint, render_template, request, jsonify, session, current_app
from sqlalchemy import desc
from werkzeug.security import check_password_hash, generate_password_hash

from db import LocalSession, User, EventLogs
from decorators import admin_required

logger = logging.getLogger(__name__)
admin_bp = Blueprint('admin', __name__)

ALLOWED_PERMISSIONS = {'user', 'Admin'}


@admin_bp.before_request
@admin_required
def restrict_admin():
    pass


@admin_bp.route('/')
def admin_panel():
    return render_template('admin/index.html')


@admin_bp.route('/users', methods=['GET'])
def get_users():
    db = LocalSession()
    try:
        users = db.query(User).all()
        user_list = [
            {"user_id": u.user_id, "username": u.username, "permissions": u.permissions}
            for u in users
        ]
        return jsonify({"users": user_list})
    except Exception:
        logger.exception("get_users failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    current_user_id = session.get('user_id')
    min_len = current_app.config.get('PASSWORD_MIN_LENGTH', 8)

    db = LocalSession()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        if 'username' in data:
            new_username = (data.get('username') or '').strip()
            if not (3 <= len(new_username) <= 64):
                return jsonify({"error": "username must be 3–64 characters"}), 400
            if new_username != user.username:
                exists = db.query(User).filter(User.username == new_username).first()
                if exists:
                    return jsonify({"error": "Username already in use"}), 409
                user.username = new_username

        if 'permissions' in data:
            new_perm = (data.get('permissions') or '').strip()
            if new_perm not in ALLOWED_PERMISSIONS:
                return jsonify({"error": "Invalid permissions value"}), 400
            # Prevent an admin from stripping their own admin rights and
            # locking everyone out.
            if user.user_id == current_user_id and new_perm != 'Admin':
                return jsonify({"error": "You cannot demote yourself"}), 400
            # Prevent demoting the last remaining admin.
            if user.permissions == 'Admin' and new_perm != 'Admin':
                admin_count = db.query(User).filter(User.permissions == 'Admin').count()
                if admin_count <= 1:
                    return jsonify(
                        {"error": "Cannot demote the last remaining admin"}
                    ), 400
            user.permissions = new_perm

        if 'password' in data and data.get('password'):
            new_password = data['password']
            if len(new_password) < min_len:
                return jsonify(
                    {"error": f"password must be at least {min_len} characters"}
                ), 400
            # Defence against session hijacking: before any password change
            # (including the admin's own), require the acting admin to prove
            # knowledge of their own current password.
            current_password = data.get('current_password') or ''
            requester = db.query(User).filter(User.user_id == current_user_id).first()
            if not requester or not check_password_hash(
                    requester.password_hash, current_password):
                return jsonify(
                    {"error": "current_password is required and must match "
                              "the acting admin's password"}
                ), 403
            user.password_hash = generate_password_hash(new_password)
            # Password rotated -> clear any pending lockout so the target
            # can log in immediately with the new credentials.
            user.failed_attempts = 0
            user.lockout_until = None

        db.commit()
        return jsonify({
            "success": True,
            "message": f"User '{user.username}' updated successfully"
        })
    except Exception:
        db.rollback()
        logger.exception("update_user failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()


@admin_bp.route('/logs', methods=['GET'])
def get_logs():
    db = LocalSession()
    try:
        logs = (
            db.query(EventLogs)
            .order_by(desc(EventLogs.timestamp))
            .limit(100)
            .all()
        )
        log_list = [
            {
                "id": log.id,
                "device_id": log.device_id,
                "eventtype": log.eventtype,
                "description": log.description,
                "value": log.value,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else None,
            }
            for log in logs
        ]
        return jsonify({"logs": log_list})
    except Exception:
        logger.exception("get_logs failed")
        return jsonify({"error": "Internal error"}), 500
    finally:
        db.close()
