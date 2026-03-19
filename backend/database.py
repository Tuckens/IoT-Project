from sqlalchemy import create_engine
from sqlalchemy import Integer, String, Column
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash


db_URL = "sqlite:///iot_demo.db"

engine = create_engine(db_URL)

LocalSession = sessionmaker(bind=engine)


#DATABASES - GONNA BE SEPARATE FILE

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    permissions = Column(String, default="user")

class EventLogs(Base):
    __tablename__= "logs"
    device_id = Column(Integer, primary_key=True)
    eventtype = Column(String)
    description = Column(String)

Base.metadata.create_all(engine)
#CRUD LOGIC

def create_user(username, password):
    db = LocalSession()

    try:
        existing_user = db.query(User).filter_by(username=username).first()
        if existing_user:
            print(f"User '{username}' already exists")
            return

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)

        db.add(new_user)
        db.commit()
        print("User created")

    except Exception as e:
        db.rollback()
        print("Error:", e)

    finally:
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
                
        elif "Admin" not in requester.permissions:
            print("No admin permissions")
    
        else:

            db.delete(target_user)
            db.commit()
            print("Deleted")
        
    except Exception as e:
        db.rollback()
        return f"Error: {str(e)}"

    finally:
        db.close()
    

def promote_to_admin(target_username, requester_username):
    db = LocalSession()

    try:
        target_user = db.query(User).filter(User.username == target_username).first()
        requester = db.query(User).filter(User.username == requester_username).first()
        if not target_user:
            print("User doesn't exist")
        
        elif not requester:
            print("Requester doesn't exists")
        else:
            
            target_user.permissions = "Admin"
            db.commit()
    except Exception as e:
        db.rollback()
        return f"Error: {str(e)}"
    finally:
        db.close()

#Authentification



def login(username, pasword):
    db = LocalSession()

    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print("User not found")

        elif(check_password_hash(user.password_hash, pasword)):
            print("Acess granted!")   # ACCESS ENDPOINT
        else:
            print("Incorret password!")

    except Exception as e:
        db.rollback()
        return f"Error: {str(e)}"
    finally:
        db.close()




# TO DO: TESTING
if __name__ == "__main__":
    db = LocalSession()
    existing_admin = db.query(User).filter(User.username == "Admin").first()
    if not existing_admin:
        Admin = User(username="Admin", password_hash = generate_password_hash("Admin"), permissions = "Admin")
        db.add(Admin)
        db.commit()
    db.close()
    create_user("user", "user")

    login("user", "user")
    delete_user("user", "Admin")
    login("user", "user")
