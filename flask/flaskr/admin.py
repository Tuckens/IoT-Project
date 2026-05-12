import logging
import os

from flask import (
    Blueprint, render_template, request, jsonify, session, current_app,
    send_from_directory, abort,
)
from sqlalchemy import desc
from werkzeug.security import check_password_hash, generate_password_hash

from db import (
    LocalSession, User, EventLogs,
    RECORDINGS_DIR, _valid_recording_filename,
    list_recordings, get_recording, delete_recording,
    get_setting, set_setting,
)
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


# ─── Recordings ─────────────────────────────────────────────────────────

@admin_bp.route('/recordings', methods=['GET'])
def list_recordings_route():
    try:
        from recording import recording_manager
        active = recording_manager.status()
    except Exception:
        active = None
    return jsonify({"recordings": list_recordings(), "active": active})


def _resolve_recording(rec_id: int):
    """Return (recording_row, safe_filename) or abort."""
    rec = get_recording(rec_id)
    if rec is None:
        abort(404)
    if not _valid_recording_filename(rec.filename):
        logger.error("recording id=%s has an invalid filename: %r", rec_id, rec.filename)
        abort(404)
    return rec


@admin_bp.route('/recordings/<int:rec_id>/stream', methods=['GET'])
def stream_recording(rec_id: int):
    rec = _resolve_recording(rec_id)
    # conditional=True enables HTTP range requests so the <video> element
    # can seek without fetching the whole file up front.
    return send_from_directory(
        RECORDINGS_DIR, rec.filename,
        mimetype='video/mp4', conditional=True, as_attachment=False,
    )


@admin_bp.route('/recordings/<int:rec_id>/download', methods=['GET'])
def download_recording(rec_id: int):
    rec = _resolve_recording(rec_id)
    return send_from_directory(
        RECORDINGS_DIR, rec.filename,
        mimetype='video/mp4', as_attachment=True,
        download_name=rec.filename,
    )


@admin_bp.route('/recordings/<int:rec_id>', methods=['DELETE'])
def delete_recording_route(rec_id: int):
    # Refuse to delete the active recording — stopping the encoder mid-write
    # would produce a broken file and leave picamera2 in a weird state.
    try:
        from recording import recording_manager
        active = recording_manager.status()
        if active and active.get("filename"):
            rec = get_recording(rec_id)
            if rec and rec.filename == active["filename"]:
                return jsonify({"error": "This recording is still being written"}), 409
    except Exception:
        logger.exception("recording-active check failed; proceeding with delete")

    result = delete_recording(rec_id)
    status = result.get("status", 500)
    if result.get("success"):
        return jsonify({"message": result["message"]}), status
    return jsonify({"error": result.get("error", "Internal error")}), status


# ─── Settings ───────────────────────────────────────────────────────────

# Reasonable physical bounds for a DHT22 indoor sensor. Values outside this
# range cannot trigger anything useful and likely indicate a typo.
TEMP_THRESHOLD_MIN = -20.0
TEMP_THRESHOLD_MAX = 60.0


@admin_bp.route('/settings', methods=['GET'])
def get_settings_route():
    raw = get_setting("temperature_alarm_below")
    try:
        threshold = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        threshold = None
    return jsonify({"temperature_alarm_below": threshold})


@admin_bp.route('/settings', methods=['PUT'])
def update_settings_route():
    data = request.get_json(silent=True) or {}

    if 'temperature_alarm_below' in data:
        raw = data.get('temperature_alarm_below')
        if raw is None or raw == "":
            # explicit clear -> disable temperature-triggered recording
            set_setting("temperature_alarm_below", None)
        else:
            try:
                val = float(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "temperature_alarm_below must be a number"}), 400
            if not (TEMP_THRESHOLD_MIN <= val <= TEMP_THRESHOLD_MAX):
                return jsonify(
                    {"error": f"temperature_alarm_below must be between "
                              f"{TEMP_THRESHOLD_MIN} and {TEMP_THRESHOLD_MAX} °C"}
                ), 400
            set_setting("temperature_alarm_below", val)

    return jsonify({"success": True, "message": "Settings updated"})
