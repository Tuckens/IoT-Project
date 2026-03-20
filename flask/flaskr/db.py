from sqlalchemy import create_engine, desc
from sqlalchemy import Integer, String, Column, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import DateTime
from sqlalchemy.sql import func
import os
from sqlalchemy import desc


db_URL = "sqlite:///iot_demo.db"

engine = create_engine(db_URL)

LocalSession = sessionmaker(bind=engine)


# DATABASES - GONNA BE SEPARATE FILE

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    permissions = Column(String, default="user")


class EventLogs(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer) 
    eventtype = Column(String)
    description = Column(String)
    value = Column(Float)
    timestamp = Column(DateTime, server_default=func.now())


Base.metadata.create_all(engine)
# CRUD LOGIC

def create_user(username, password):
    db = LocalSession()

    try:
        existing_user = db.query(User).filter_by(username=username).first()
        if existing_user:
            print(f"User '{username}' already exists")
            return {"success": False, "error": "User already exists", "status": 409}

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)

        db.add(new_user)
        db.commit()
        return {"success": True, "message": "User created successfully", "status": 201}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e), "status": 500}

    finally:
        db.close()


def delete_user(target_username, requester_username):
    db = LocalSession()

    try:
        target_user = db.query(User).filter(
            User.username == target_username).first()
        if not target_user:
            return {"success": False, "error": "The user doesn't exists", "status": 404}

        requester = db.query(User).filter(
            User.username == requester_username).first()
        if not requester:
            return {"success": False, "error": "Wrong requester", "status": 422}

        elif "Admin" not in requester.permissions:
            return {"success": False, "error": "No admin permissions", "status": 403}

        else:

            db.delete(target_user)
            db.commit()
            return {"success": True, "message": f"You deleted {target_user}", "status": 201}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e), "status": 400}

    finally:
        db.close()


def promote_to_admin(target_username, requester_username):
    db = LocalSession()

    try:
        target_user = db.query(User).filter(
            User.username == target_username).first()
        requester = db.query(User).filter(
            User.username == requester_username).first()
        if not target_user:
            return {"success": False, "error": "No user found", "status": 404}

        elif not requester:
            return {"success": False, "error": "Nice try", "status": 400}
        else:

            target_user.permissions = "Admin"
            db.commit()
            return {"success": True, "message": f"{target_username} got promoted to an admin", "status": 200}
    except Exception as e:
        db.rollback()
        return {"success": False, "Error": {str(e)}, "status": 400}
    finally:
        db.close()

# Authentification


def login(username, pasword):
    db = LocalSession()

    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return {"success": False, "error": "User not found", "status": 404}

        elif (check_password_hash(user.password_hash, pasword)):
            print("logged")
            return {"success": True, "message": "Welcome", "status": 200}
            
        else:
            return {"success": False, "error": "Wrong password", "status": 400}

    except Exception as e:
        db.rollback()
        return f"Error: {str(e)}"
    finally:
        db.close()


#DATA
def log_sensor_data(device_id, event_type, description, val):
    db = LocalSession()
    try:
        new_log = EventLogs(device_id = device_id, eventtype = event_type, description = description, value = val)
        db.add(new_log)
        db.commit()
        return {"success": True, "message": "log uploaded", "status": 200}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": "not uploaded", "status": 400}
    finally:
        db.close()

def record_camera_event(filename):
    db = LocalSession()
    try:
        file_path = os.path.join("static/recordings", filename)
        new_recording = EventLogs(eventtype = "Recording", description = filename, value=os.path.getsize(f"/home/pi/flaskr/{file_path}"))

        db.add(new_recording)
        db.commit()
        return {"success": True, "message": "Recording saved", "status": 200}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": "Exception", "status": 400}
    finally:
        db.close()

def get_recent_readings(limit=20):
    db = LocalSession()
    try:
        readings = db.query(EventLogs)\
                     .order_by(desc(EventLogs.timestamp))\
                     .limit(limit)\
                     .all()

        readings.reverse()
        chart_data = {
            "labels": [r.timestamp.strftime("%H:%M:%S") for r in readings],
            "values": [r.value for r in readings],
            "count": len(readings)
        }
        return chart_data
    except Exception as e:
        print(f"Chart Data Error: {e}")
        return {"labels": [], "values": [], "error": str(e)}
    finally:
        db.close()

def del_sensor_data(device_id, permissions):
    db = LocalSession()
    try:
        del_log = db.query(EventLogs).filter(EventLogs.device_id == device_id)
        if permissions != "Admin":
            return {"success": False, "error": "no permissions", "status": 403}
        else:
            db.delete(del_log)
            db.commit()
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e), "status": 400 }
    finally:
        db.close()



# TESTING
if __name__ == "__main__":
    db = LocalSession()
    existing_admin = db.query(User).filter(User.username == "Admin").first()
    if not existing_admin:
        Admin = User(username="Admin", password_hash=generate_password_hash("Admin"), permissions="Admin")
        db.add(Admin)
        db.commit()
    db.close()

    for i in range(200):
        log_sensor_data(1, "temperature", "normal", i)

