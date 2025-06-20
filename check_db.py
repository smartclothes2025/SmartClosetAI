from app.core.db import SessionLocal
from app.models.auth import User

db = SessionLocal()

users = db.query(User).all()


for user in users:
    print(f"User: {user.username}, Email: {user.email}")
   