import os
import logging
from datetime import datetime, timedelta

from sqlalchemy import create_engine, desc, text, func
from sqlalchemy import Integer, Float, String, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

_DB_DIR = os.path.dirname(os.path.abspath(__file__))
db_URL = f"sqlite:///{os.path.join(_DB_DIR, 'iot_demo.db')}"

# Video recordings live outside flask/flaskr/static/ so Nginx does not serve
# them as public assets. Every download goes through an @admin_required Flask
# endpoint.
RECORDINGS_DIR = os.path.join(_DB_DIR, 'recordings')
os.makedirs(RECORDINGS_DIR, exist_ok=True)

engine = create_engine(db_URL)
LocalSession = sessionmaker(bind=engine)

# Lockout policy — resists distributed brute force even when attackers
# rotate IPs so per-IP rate limits don't help. A single account takes at
# most MAX_FAILED_ATTEMPTS bad passwords before being iced.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

# Used to equalise timing when the username does not exist, to avoid a
# "user-not-found returns in 0.1 ms, bad-password returns in 50 ms" leak.
_TIMING_DUMMY_HASH = generate_password_hash('x' * 16)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    permissions: Mapped[str] = mapped_column(String, default="user")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lockout_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EventLogs(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer)
    eventtype: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    value: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)







Base.metadata.create_all(engine)


def _ensure_schema() -> None:
    """SQLite ALTER TABLE migration for the lockout columns.

    create_all() only creates missing tables; it does not add missing
    columns to existing tables. We hand-roll the migration so upgrading
    an existing deployment does not require dropping iot_demo.db.
    """
    with engine.begin() as conn:
        existing = {
            row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if 'failed_attempts' not in existing:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0"
            ))
            logger.info("schema: added users.failed_attempts")
        if 'lockout_until' not in existing:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN lockout_until DATETIME"
            ))
            logger.info("schema: added users.lockout_until")


_ensure_schema()


def cleanup_old_recordings(max_age_days: int = 7, max_count: int = 100) -> None:
    """Purge old recordings to keep SD-card usage bounded.

    Called on a schedule (see app.py). Deletes rows older than
    max_age_days, then trims to the max_count most recent rows. The
    underlying .mp4 files are unlinked too; missing files are tolerated.

    Important: stream/download endpoints that are holding an open file
    descriptor during the delete continue working — on Linux the file
    data stays reachable via the fd until it's closed.
    """
    db = LocalSession()
    victims = []
    try:
        cutoff = datetime.now() - timedelta(days=max_age_days)

        # Age-based sweep.
        old_rows = db.query(Recording).filter(Recording.started_at < cutoff).all()
        for r in old_rows:
            victims.append(r)

        # Count-based sweep — keep the newest max_count, drop the rest.
        if old_rows:
            surplus = (
                db.query(Recording)
                .filter(~Recording.id.in_([r.id for r in old_rows]))
                .order_by(desc(Recording.started_at))
                .offset(max_count)
                .all()
            )
        else:
            surplus = (
                db.query(Recording)
                .order_by(desc(Recording.started_at))
                .offset(max_count)
                .all()
            )
        for r in surplus:
            victims.append(r)

        for r in victims:
            if _valid_recording_filename(r.filename):
                path = os.path.join(RECORDINGS_DIR, r.filename)
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    logger.exception("cleanup: failed to rm %s", r.filename)
            db.delete(r)

        db.commit()
        if victims:
            logger.info("cleanup: deleted %d old recording(s)", len(victims))
    except Exception:
        db.rollback()
        logger.exception("cleanup_old_recordings failed")
    finally:
        db.close()


def cleanup_old_logs(max_age_hours: int = 24) -> None:
    db = LocalSession()
    try:
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        deleted = db.query(EventLogs).filter(EventLogs.timestamp < cutoff).delete()
        db.commit()
        logger.info("cleanup: deleted %d old log(s)", deleted)
    except Exception:
        db.rollback()
        logger.exception("cleanup_old_logs failed")
    finally:
        db.close()


def create_user(username: str, password: str) -> dict:
    db = LocalSession()
    try:
        if db.query(User).filter_by(username=username).first():
            return {"success": False, "error": "User already exists", "status": 409}

        new_user = User(username=username, password_hash=generate_password_hash(password))
        db.add(new_user)
        db.commit()
        return {"success": True, "message": "User created successfully", "status": 201}
    except Exception:
        db.rollback()
        logger.exception("create_user failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def delete_user(target_username: str, requester_username: str) -> dict:
    db = LocalSession()
    try:
        result = db.execute(text("SELECT user_id, permissions FROM users WHERE username = :u"), {"u": target_username}).first()
        if result is None:
            return {"success": False, "error": "User not found", "status": 404}
        target_id, target_perms = result

        result = db.execute(text("SELECT user_id, permissions FROM users WHERE username = :u"), {"u": requester_username}).first()
        if result is None:
            return {"success": False, "error": "Requester not found", "status": 401}
        requester_id, requester_perms = result

        if requester_perms != 'Admin':
            return {"success": False, "error": "Admin permission required", "status": 403}

        # Refuse to delete the last admin — it locks everyone out of the admin
        # panel and forces a CLI recovery via db.py bootstrap-admin.
        if target_perms == 'Admin':
            admin_count = db.execute(text("SELECT COUNT(*) FROM users WHERE permissions = 'Admin'")).scalar()
            if admin_count is not None and admin_count <= 1:
                return {
                    "success": False,
                    "error": "Cannot delete the last remaining admin",
                    "status": 400,
                }

        db.execute(text("DELETE FROM users WHERE user_id = :id"), {"id": target_id})
        db.commit()
        return {"success": True, "message": f"Deleted user {target_username}", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("delete_user failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def promote_to_admin(target_username: str, requester_username: str) -> dict:
    db = LocalSession()
    try:
        result = db.execute(text("SELECT user_id, permissions FROM users WHERE username = :u"), {"u": requester_username}).first()
        if result is None:
            return {"success": False, "error": "Requester not found", "status": 401}
        requester_id, requester_perms = result
        
        if requester_perms != 'Admin':
            return {"success": False, "error": "Admin permission required", "status": 403}

        result = db.execute(text("SELECT user_id FROM users WHERE username = :u"), {"u": target_username}).first()
        if result is None:
            return {"success": False, "error": "User not found", "status": 404}
        target_id = result[0]

        db.execute(text("UPDATE users SET permissions = :p WHERE user_id = :id"), {"p": "Admin", "id": target_id})
        db.commit()
        return {"success": True, "message": f"{target_username} promoted to Admin", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("promote_to_admin failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def login(username: str, password: str) -> dict:
    db = LocalSession()
    try:
        result = db.execute(text("SELECT user_id, password_hash, lockout_until, failed_attempts FROM users WHERE username = :u"), {"u": username}).first()
        now = datetime.now()

        if result is None:
            # Still run a hash to keep the branch timing indistinguishable
            # from the "user exists, wrong password" case.
            check_password_hash(_TIMING_DUMMY_HASH, password)
            return {"success": False, "error": "Invalid credentials", "status": 401}

        user_id, password_hash, lockout_until, failed_attempts = result

        # Account-level lockout — survives per-IP rotation (which defeats
        # Flask-Limiter alone).
        if lockout_until is not None and lockout_until > now:
            remaining = int((lockout_until - now).total_seconds())
            return {
                "success": False,
                "error": f"Account locked. Try again in {remaining} s.",
                "status": 429,
            }

        password_hash_str = password_hash if password_hash else ""
        if not check_password_hash(password_hash_str, password):
            failed_count = (failed_attempts or 0) + 1
            if failed_count >= MAX_FAILED_ATTEMPTS:
                db.execute(text("UPDATE users SET lockout_until = :t, failed_attempts = 0 WHERE user_id = :id"), {"t": now + LOCKOUT_DURATION, "id": user_id})
                logger.warning(
                    "Account %r locked for %d min after %d failed attempts",
                    username, int(LOCKOUT_DURATION.total_seconds() // 60),
                    MAX_FAILED_ATTEMPTS,
                )
            else:
                db.execute(text("UPDATE users SET failed_attempts = :f WHERE user_id = :id"), {"f": failed_count, "id": user_id})
            db.commit()
            return {"success": False, "error": "Invalid credentials", "status": 401}

        # Successful login — reset counters.
        db.execute(text("UPDATE users SET failed_attempts = 0, lockout_until = NULL WHERE user_id = :id"), {"id": user_id})
        db.commit()

        # Get updated user info
        result = db.execute(text("SELECT user_id, username, permissions FROM users WHERE user_id = :id"), {"id": user_id}).first()
        if result:
            user_id, uname, perms = result
            return {
                "success": True,
                "message": "Welcome",
                "status": 200,
                "user_id": user_id,
                "username": uname,
                "permissions": perms,
            }
        return {"success": True, "message": "Welcome", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("login failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()

def log_sensor_data(device_id, event_type, description, val):
    db = LocalSession()
    try:
        new_log = EventLogs(device_id = device_id, eventtype = event_type, description = description, value = val)
        db.add(new_log)
        db.commit()
        return {"success": True, "message": "log uploaded", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("log_sensor_data failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def record_camera_event(filename):
    db = LocalSession()
    try:
        file_path = os.path.join("static/recordings", filename)
        abs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_path)
        size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0
        new_recording = EventLogs(eventtype="Recording", description=filename, value=size)
        db.add(new_recording)
        db.commit()
        return {"success": True, "message": "Recording saved", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("record_camera_event failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


import re as _re

# Server-generated filenames only — this regex is the gate on every filesystem
# operation touching recordings/. Path traversal is impossible because no caller
# supplies a filename; we look them up by id.
RECORDING_FILENAME_RE = _re.compile(r'^\d{8}-\d{6}_(motion|temperature)\.mp4$')


def _valid_recording_filename(name: str) -> bool:
    return bool(RECORDING_FILENAME_RE.match(name or ''))


def create_recording_row(filename: str, trigger: str) -> int:
    db = LocalSession()
    try:
        db.execute(text("INSERT INTO recordings (filename, trigger, started_at) VALUES (:f, :t, :s)"), 
                   {"f": filename, "t": trigger, "s": datetime.now()})
        db.commit()
        result = db.execute(text("SELECT id FROM recordings WHERE filename = :f"), {"f": filename}).first()
        return result[0] if result else -1
    except Exception:
        db.rollback()
        return -1
    finally:
        db.close()


def finalise_recording_row(rec_id: int, duration_s: float, size_bytes: int) -> None:
    """Finalize a recording row with its duration and file size."""
    db = LocalSession()
    try:
        db.execute(text("UPDATE recordings SET ended_at = :e, duration_s = :d, size_bytes = :s WHERE id = :id"), 
                   {"e": datetime.now(), "d": duration_s, "s": size_bytes, "id": rec_id})
        db.commit()
    finally:
        db.close()



def get_recording_list(limit=20):
    db = LocalSession()
    try:
        rows = (
            db.query(Recording)
            .order_by(desc(Recording.started_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "filename": r.filename,
                "trigger": r.trigger,
                "started_at": r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at is not None else None,
                "ended_at": r.ended_at.strftime("%Y-%m-%d %H:%M:%S") if r.ended_at is not None else None,
                "duration_s": r.duration_s,
                "size_bytes": r.size_bytes,
                "ready": r.ended_at is not None,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_recording(rec_id: int):
    db = LocalSession()
    try:
        return db.query(Recording).filter(Recording.id == rec_id).first()
    finally:
        db.close()


def delete_recording(rec_id: int) -> dict:
    db = LocalSession()
    try:
        result = db.execute(text("SELECT filename FROM recordings WHERE id = :id"), {"id": rec_id}).first()
        if result is None:
            return {"success": False, "error": "Recording not found", "status": 404}
        rec_filename = result[0]
        if not _valid_recording_filename(rec_filename):
            return {"success": False, "error": "Invalid filename on row", "status": 500}
        path = os.path.join(RECORDINGS_DIR, rec_filename)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.exception("failed to remove recording file")
        db.execute(text("DELETE FROM recordings WHERE id = :id"), {"id": rec_id})
        db.commit()
        return {"success": True, "message": "Recording deleted", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("delete_recording failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def get_setting(key: str, default=None):
    db = LocalSession()
    try:
        result = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key}).first()
        return result[0] if result else default
    finally:
        db.close()


def set_setting(key: str, value) -> None:
    db = LocalSession()
    try:
        s = db.query(AppSetting).filter(AppSetting.key == key).first()
        if s is None:
            new_value = None if value is None else str(value)
            db.add(AppSetting(key=key, value=new_value))
        else:
            new_value = None if value is None else str(value)
            db.execute(text("UPDATE app_settings SET value = :v WHERE key = :k"), {"v": new_value, "k": key})
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("set_setting failed")
        raise
    finally:
        db.close()


def get_recent_readings(limit: int = 20) -> dict:
    db = LocalSession()
    try:
        readings = (
            db.query(EventLogs)
            .order_by(desc(EventLogs.timestamp))
            .limit(limit)
            .all()
        )
        readings.reverse()
        return {
            "labels": [r.timestamp.strftime("%H:%M:%S") if r.timestamp is not None else "" for r in readings],
            "values": [r.value for r in readings],
            "count": len(readings),
        }
    except Exception:
        logger.exception("get_recent_readings failed")
        return {"labels": [], "values": [], "count": 0}
    finally:
        db.close()

# TESTING
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python db.py <username> <password>")
        sys.exit(1)
    username = sys.argv[1]
    password = sys.argv[2]
    db = LocalSession()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing is not None:
            print(f"Admin user {username!r} already exists — nothing to do.")
        else:
            admin = User(
                username=username,
                password_hash=generate_password_hash(password),
                permissions="Admin",
            )
            db.add(admin)
            db.commit()
            print(f"Created admin user {username!r}.")
    finally:
        db.close()

