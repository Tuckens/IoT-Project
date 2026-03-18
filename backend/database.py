from sqlalchemy import create_engine
from sqlalchemy import Integer, String, Column
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase


db_URL = "UNKOWN"

engine = create_engine(db_URL)

LocalSession = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    permissions = Column(String)

class EventLogs(Base):
    __tablename__= "logs"
    device_id = Column(Integer, primary_key=True)
    eventtype = Column(String)
    description = Column(String)

def create_user(username, password, permissions):
    db = LocalSession()
    try:
        new_user = User(username = username, password_hash = password, permissions = permissions)

        if(new_user == db.query(User).filter(User.username == username).first()):
            print("This user already exists")
        else:
            db.add(new_user)
            db.commit()
    except:
        print("This user already exists")
    db.close()

def delete_user(target_username, requester_username):
    db = LocalSession()

    
    try:
        target_user = db.query(User).filter(User.username == target_username).first()
        if not target_user:
            print("The user doesn't exists")
           

        requester = db.query(User).filter(User.username == requester_username).first()
        if not requester:
            print("Requester doesn't exists")
                


        if "admin" not in requester.permissions:
            print("No admin permissions")
    
        else:

            db.delete()
            db.commit()

    finally:
        db.close()
        

