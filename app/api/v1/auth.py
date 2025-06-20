

#api/v1/auth.py
from fastapi import APIRouter, HTTPException, Depends, Form, Request
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String
from fastapi.security import OAuth2PasswordBearer
from app.core.db import Base, get_db
from app.models.auth import User
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
import os
import logging
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, initialize_app, _apps
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 初始化 Firebase Admin（只初始化一次）
if not _apps:
    firebase_key_path = os.getenv("FIREBASE_KEY_PATH")
    if not firebase_key_path or not os.path.exists(firebase_key_path):
        raise FileNotFoundError(f"[錯誤] 找不到 Firebase 金鑰檔案，請確認環境變數 FIREBASE_KEY_PATH 設定正確，目前值：{firebase_key_path}")
    
    cred = credentials.Certificate(firebase_key_path)
    initialize_app(cred)
from firebase_admin import credentials, auth as firebase_auth

# 初始化 Firebase Admin（只初始化一次）
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-admin-key.json")
    firebase_admin.initialize_app(cred)

logging.basicConfig(level=logging.INFO)

router = APIRouter()

# 驗證 Token 的函數（可加到 Depends 使用）
def verify_firebase_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    id_token = auth_header.split(" ")[1]
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

def get_current_user(
    decoded_token: dict = Depends(verify_firebase_token),
    db: Session = Depends(get_db)
):
    firebase_uid = decoded_token.get("uid")
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    return user

@router.get("/ping")
def ping():
    return {"message": "pong"}

@router.post("/register")
def register_by_firebase(
    decoded_token: dict = Depends(verify_firebase_token),
    username: str = Form(...),
    db: Session = Depends(get_db)
):
    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="使用者名稱已被註冊")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="電子郵件已被註冊")

    new_user = User(username=username, email=email, firebase_uid=firebase_uid)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"msg": "使用者建立成功"}

@router.post("/login")
def firebase_login(decoded_token: dict = Depends(verify_firebase_token)):
    return {
        "message": "Firebase 驗證成功",
        "uid": decoded_token.get("uid"),
        "email": decoded_token.get("email")
    }

@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "username": user.username,
        "email": user.email,
        "firebase_uid": user.firebase_uid
    }



# from fastapi import APIRouter, Depends
# from sqlalchemy.orm import Session
# from app.core.db import get_db
# from app.models.auth import User

# router = APIRouter()

# def get_current_user(db: Session = Depends(get_db)):
#     # 固定使用測試用戶，避免需要輸入任何東西
#     username = "測試用戶"
#     email = "testuser@example.com"
#     user = db.query(User).filter(User.username == username).first()
#     if not user:
#         user = User(username=username, email=email, password= devtest123)
#         db.add(user)
#         db.commit()
#         db.refresh(user)
#     return user

# @router.get("/me")
# def get_me(user: User = Depends(get_current_user)):
#     return {
#         "username": user.username,
#         "email": user.email
#     }

 