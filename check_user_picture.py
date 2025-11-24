"""
Check if current user has profile picture
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.db import get_db
from app.models.auth import User

db = next(get_db())

print("="*60)
print("User Picture Status Check")
print("="*60)

users = db.query(User).all()

print(f"\nTotal users: {len(users)}\n")

has_picture = []
no_picture = []

for user in users:
    email = getattr(user, 'email', 'Unknown')
    picture = getattr(user, 'picture', None)
    
    if picture:
        has_picture.append((email, picture))
    else:
        no_picture.append(email)

print(f"Users WITH picture ({len(has_picture)}):")
for email, pic in has_picture:
    print(f"  [OK] {email}")
    print(f"       Picture: {pic}\n")

print(f"\nUsers WITHOUT picture ({len(no_picture)}):")
for email in no_picture:
    print(f"  [X] {email}")

print("\n" + "="*60)
print("SOLUTION:")
print("="*60)
print("If you're testing with an account that has NO picture:")
print("1. Upload a profile picture in the frontend")
print("2. Or use 'abcde@gmail.com' which has a picture")
print("3. Then test the chat assistant again")
print("="*60)
