from sqlalchemy import create_engine
from sqlalchemy import Integer, String, Column
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase


db_URL = "UNKOWN"

engine = create_engine(db_URL)

LocalSession = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass

class User(DeclarativeBase):
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

    new_user = User(username = username, password_hash = password, permissions = permissions)

    if()
    db.add(new_user)
    db.commit()

    db.close()

