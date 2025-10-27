#auth.py
from fastapi import APIRouter, HTTPException, Depends, Form, Request, Body
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.auth import User
from passlib.context import CryptContext
import logging
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, _apps
from dotenv import load_dotenv
from datetime import datetime, timezone
import os
import uuid as _uuid
import google.auth
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()

firebase_key_path = os.getenv("FIREBASE_KEY_PATH")
if not firebase_key_path or not os.path.exists(firebase_key_path):
    raise FileNotFoundError(f"[錯誤] 找不到 Firebase 金鑰檔案，目前值：{firebase_key_path}")

if not _apps:
    cred = credentials.Certificate("firebase-admin-key.json") 
    firebase_admin.initialize_app(cred)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Common constants to avoid literal duplication and ease maintenance
AUTH_BEARER_PREFIX = "Bearer "
ERR_INVALID_TOKEN = "Token 無效"
ERR_USER_NOT_FOUND = "使用者不存在"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# 驗證 Firebase Token
def verify_firebase_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(AUTH_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    id_token = auth_header.split(" ")[1]
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        logging.info(f"Firebase token 驗證成功: {decoded_token['email']}")
        return decoded_token
    except Exception as e:
        logging.error(f"Firebase token 驗證失敗: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid Firebase token")


def get_current_user(request: Request, db: Session = Depends(get_db), token: str = Form(None)):
    """
    從 Header 的 Authorization Bearer token 或 Form 中的 token 進行驗證。
    臨時用的簡易 token：格式為 "user-<uuid>-token"。
    """
    # 優先從 Header 中獲取 Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    
    # 如果沒有獲得 token，檢查 Form 中的 token
    if not token:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    prefix = "user-"
    suffix = "-token"
    if not isinstance(token, str) or not token.startswith(prefix) or not token.endswith(suffix):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    # 只移除前後綴，保留中間的完整 UUID（含連字符）
    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix)+len(suffix)) else ""
    # 驗證 UUID 格式，避免傳入無效字串造成 DB Driver 錯誤
    try:
        _uuid.UUID(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)
    return user


@router.get("/ping")
def ping():
    return {"message": "pong"}


@router.get("/users")
def list_users(limit: int = 100, db: Session = Depends(get_db)):
    """列出使用者清單（簡單版）。建議後續加上權限保護。"""
    users = db.query(User).limit(limit).all()
    return [
        {
            "id": u.id,
            "email": getattr(u, "email", None),
            "display_name": getattr(u, "display_name", None),
            "role": getattr(u, "role", None) or "user",
            "created_at": getattr(u, "created_at", None).isoformat() if getattr(u, "created_at", None) else None,
        }
        for u in users
    ]


@router.post("/register")
def register_user(
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email 已被註冊")

    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
        role="user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
      "token": f"user-{user.id}-token",
            "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}
    }


@router.post("/login/")
def login_user(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(None),
    password: str = Form(None)
):
    # 1. 嘗試用 Firebase Token 驗證
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        id_token = auth_header.split(" ")[1]
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            email_from_token = decoded_token.get("email")
            display_name = decoded_token.get("name") or email_from_token or "User"
            user = db.query(User).filter(User.email == email_from_token).first()
            if not user:
                # 若本地沒資料，自動補一筆
                user = User(
                    email=email_from_token,
                    display_name=display_name,
                    password_hash=None,
                    firebase_uid=decoded_token.get("uid"),
                    role="user"
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            return {
                "token": f"user-{user.id}-token",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role or "user"
                }
            }
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Firebase token 驗證失敗: {str(e)}")

    # 2. 沒帶 Token，走本地帳密驗證
    if not email or not password:
        raise HTTPException(status_code=400, detail="請提供 email 和 password 或 Firebase Token")

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    return {
        "token": f"user-{user.id}-token",
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role or "user"
        }
    }


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    """刪除使用者（簡單版，後續應加入管理者權限檢查）。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    db.delete(user)
    db.commit()
    return {"status": "ok"}

class RoleUpdate(BaseModel):
    role: str

@router.put("/users/{user_id}/role")
def update_user_role(user_id: str, payload: RoleUpdate, request: Request, db: Session = Depends(get_db)):

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(AUTH_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    caller_id_raw = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    # try convert to int when possible (DB id is Integer in this project)
    try:
        caller_id = int(caller_id_raw)
    except Exception:
        caller_id = caller_id_raw

    caller = db.query(User).filter(User.id == caller_id).first()
    if not caller:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)

    # find target user
    try:
        target_id = int(user_id)
    except Exception:
        target_id = user_id

    target = db.query(User).filter(User.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="使用者不存在")

    if not payload.role or not isinstance(payload.role, str):
        raise HTTPException(status_code=400, detail="請提供有效的 role")

    target.role = payload.role
    db.commit()
    db.refresh(target)

    return {
        "id": target.id,
        "role": target.role,
    }



@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """
    以 Authorization Bearer user-<id>-token 取得當前使用者，
    回傳 app_users (User) 的 display_name 與 email。
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(AUTH_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    if not user_id:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)

    return {
        "email": getattr(user, "email", None),
        "display_name": getattr(user, "display_name", None),
        "interformation": getattr(user, "interformation", None),
    }


@router.get("/test-firebase")
def test_firebase():
    test_email = f"test{int(datetime.now(timezone.utc).timestamp())}@example.com"
    test_password = "Test1234"
    test_display_name = "測試用戶"

    try:
        user_record = firebase_auth.create_user(
            email=test_email,
            password=test_password,
            display_name=test_display_name
        )
        firebase_auth.delete_user(user_record.uid)
        return {
            "msg": "Firebase 測試成功",
            "email": test_email
        }
    except Exception as e:
        return {"msg": "Firebase 測試失敗", "error": str(e)}


@router.get("/debug/gcloud")
def debug_gcloud():
    """Debug endpoint: show which Google credentials and project are being used by the server.

    Note: this will not return any private key contents. It returns credential type, project id,
    client/service account email when available, and related env vars (GCS bucket, upload switch).
    """
    try:
        creds, project = google.auth.default()
    except Exception as e:
        return {"error": f"google.auth.default() failed: {e}"}

    email = getattr(creds, "service_account_email", None) or getattr(creds, "client_email", None)
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    gac_name = None
    if gac:
        try:
            gac_name = gac.split(os.sep)[-1]
        except Exception:
            gac_name = gac

    return {
        "project": project,
        "credential_type": type(creds).__name__,
        "credential_email": email,
        "GOOGLE_APPLICATION_CREDENTIALS": gac_name,
        "GCS_BUCKET_NAME": os.getenv("GCS_BUCKET_NAME"),
        "UPLOAD_TO_GCS": os.getenv("UPLOAD_TO_GCS"),
    }

