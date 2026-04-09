from flask import Blueprint, render_template, request, jsonify
from db import LocalSession, User, EventLogs
from sqlalchemy import desc
from werkzeug.security import generate_password_hash

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
def admin_panel():
    """Serve the admin dashboard page."""
    return render_template('admin/index.html')


@admin_bp.route('/users', methods=['GET'])
def get_users():
    """Return a JSON list of all users."""
    db = LocalSession()
    try:
        users = db.query(User).all()
        user_list = [
            {
                "user_id": u.user_id,
                "username": u.username,
                "permissions": u.permissions
            }
            for u in users
        ]
        return jsonify({"users": user_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user information (username, password, permissions)."""
    db = LocalSession()
    try:
        data = request.get_json()

        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        if 'username' in data and data['username'].strip():
            user.username = data['username'].strip()
        if 'permissions' in data and data['permissions'].strip():
            user.permissions = data['permissions'].strip()
        if 'password' in data and data['password'].strip():
            user.password_hash = generate_password_hash(data['password'].strip())

        db.commit()
        return jsonify({
            "success": True,
            "message": f"User '{user.username}' updated successfully"
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@admin_bp.route('/logs', methods=['GET'])
def get_logs():
    """Return the last 100 event logs from the database."""
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
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else None
            }
            for log in logs
        ]
        return jsonify({"logs": log_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
