import os
import logging
from datetime import datetime, timedelta

from sqlalchemy import create_engine, desc, text
from sqlalchemy import Integer, Float, String, Column, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

_DB_DIR = os.path.dirname(os.path.abspath(__file__))
db_URL = f"sqlite:///{os.path.join(_DB_DIR, 'iot_demo.db')}"

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
    user_id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    permissions = Column(String, default="user")
    failed_attempts = Column(Integer, default=0)
    lockout_until = Column(DateTime, nullable=True)


class EventLogs(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer)
    eventtype = Column(String)
    description = Column(String)
    value = Column(Float)
    timestamp = Column(DateTime, default=datetime.now)


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
        target_user = db.query(User).filter(User.username == target_username).first()
        if not target_user:
            return {"success": False, "error": "User not found", "status": 404}

        requester = db.query(User).filter(User.username == requester_username).first()
        if not requester:
            return {"success": False, "error": "Requester not found", "status": 401}

        if requester.permissions != 'Admin':
            return {"success": False, "error": "Admin permission required", "status": 403}

        # Refuse to delete the last admin — it locks everyone out of the admin
        # panel and forces a CLI recovery via db.py bootstrap-admin.
        if target_user.permissions == 'Admin':
            admin_count = db.query(User).filter(User.permissions == 'Admin').count()
            if admin_count <= 1:
                return {
                    "success": False,
                    "error": "Cannot delete the last remaining admin",
                    "status": 400,
                }

        deleted_name = target_user.username
        db.delete(target_user)
        db.commit()
        return {"success": True, "message": f"Deleted user {deleted_name}", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("delete_user failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def promote_to_admin(target_username: str, requester_username: str) -> dict:
    db = LocalSession()
    try:
        requester = db.query(User).filter(User.username == requester_username).first()
        if not requester:
            return {"success": False, "error": "Requester not found", "status": 401}
        if requester.permissions != 'Admin':
            return {"success": False, "error": "Admin permission required", "status": 403}

        target_user = db.query(User).filter(User.username == target_username).first()
        if not target_user:
            return {"success": False, "error": "User not found", "status": 404}

        target_user.permissions = "Admin"
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
        user = db.query(User).filter(User.username == username).first()
        now = datetime.now()

        if not user:
            # Still run a hash to keep the branch timing indistinguishable
            # from the "user exists, wrong password" case.
            check_password_hash(_TIMING_DUMMY_HASH, password)
            return {"success": False, "error": "Invalid credentials", "status": 401}

        # Account-level lockout — survives per-IP rotation (which defeats
        # Flask-Limiter alone).
        if user.lockout_until and user.lockout_until > now:
            remaining = int((user.lockout_until - now).total_seconds())
            return {
                "success": False,
                "error": f"Account locked. Try again in {remaining} s.",
                "status": 429,
            }

        if not check_password_hash(user.password_hash, password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.lockout_until = now + LOCKOUT_DURATION
                user.failed_attempts = 0
                logger.warning(
                    "Account %r locked for %d min after %d failed attempts",
                    user.username, int(LOCKOUT_DURATION.total_seconds() // 60),
                    MAX_FAILED_ATTEMPTS,
                )
            db.commit()
            return {"success": False, "error": "Invalid credentials", "status": 401}

        # Successful login — reset counters.
        user.failed_attempts = 0
        user.lockout_until = None
        db.commit()

        return {
            "success": True,
            "message": "Welcome",
            "status": 200,
            "user_id": user.user_id,
            "username": user.username,
            "permissions": user.permissions,
        }
    except Exception:
        db.rollback()
        logger.exception("login failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def log_sensor_data(event_type: str, description: str, val: float) -> dict:
    db = LocalSession()
    try:
        new_log = EventLogs(eventtype=event_type, description=description, value=val)
        db.add(new_log)
        db.commit()
        return {"success": True, "message": "log uploaded", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("log_sensor_data failed")
        return {"success": False, "error": "Internal error", "status": 500}
    finally:
        db.close()


def record_camera_event(filename: str) -> dict:
    # Basic filename sanitation — prevent traversal from the raw JSON field.
    safe = os.path.basename(filename)
    if safe != filename or not safe:
        return {"success": False, "error": "Invalid filename", "status": 400}

    db = LocalSession()
    try:
        file_path = os.path.join("static/recordings", safe)
        abs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_path)
        size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0
        new_recording = EventLogs(eventtype="Recording", description=safe, value=size)
        db.add(new_recording)
        db.commit()
        return {"success": True, "message": "Recording saved", "status": 200}
    except Exception:
        db.rollback()
        logger.exception("record_camera_event failed")
        return {"success": False, "error": "Internal error", "status": 500}
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
            "labels": [r.timestamp.strftime("%H:%M:%S") for r in readings],
            "values": [r.value for r in readings],
            "count": len(readings),
        }
    except Exception:
        logger.exception("get_recent_readings failed")
        return {"labels": [], "values": [], "count": 0}
    finally:
        db.close()


def _create_initial_admin() -> None:
    """One-off CLI helper: python db.py bootstrap-admin."""
    username = os.environ.get('BOOTSTRAP_ADMIN_USERNAME')
    password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD')
    if not username or not password:
        raise RuntimeError(
            "Set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD "
            "in the environment before running bootstrap-admin."
        )
    if len(password) < 8:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 8 characters.")

    db = LocalSession()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"Admin user {username!r} already exists — nothing to do.")
            return
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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap-admin":
        _create_initial_admin()
    else:
        print("Usage: BOOTSTRAP_ADMIN_USERNAME=... BOOTSTRAP_ADMIN_PASSWORD=... "
              "python db.py bootstrap-admin")
