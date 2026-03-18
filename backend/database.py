from sqlalchemy import create_engine
from sqlalchemy import Integer, String, Column
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase


db_URL = "UNKOWN"

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
    permissions = Column(String)

class EventLogs(Base):
    __tablename__= "logs"
    device_id = Column(Integer, primary_key=True)
    eventtype = Column(String)
    description = Column(String)

#CRUD LOGIC

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
                
        elif "admin" not in requester.permissions:
            print("No admin permissions")
    
        else:

            db.delete()
            db.commit()
        
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


def hashing(input):
    output = ###TO DO
    return output

def check_password_hash(db_password, sent_password):
    if(hashing(sent_password) == db_password): return True


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


