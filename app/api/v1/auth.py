# app/api/v1/auth.py
from fastapi import APIRouter, HTTPException, Depends, Form, Request
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
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# 讀取 Firebase 金鑰路徑（優先用環境變數）
firebase_key_path = os.getenv("FIREBASE_KEY_PATH") or "firebase-admin-key.json"
if not os.path.exists(firebase_key_path):
    raise FileNotFoundError(f"[錯誤] 找不到 Firebase 金鑰檔案，目前值：{firebase_key_path}")

# 初始化 Firebase（避免重複初始化）
if not _apps:
    cred = credentials.Certificate(firebase_key_path)
    firebase_admin.initialize_app(cred)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 共用常數
AUTH_BEARER_PREFIX = "Bearer "
ERR_INVALID_TOKEN = "Token 無效"
ERR_USER_NOT_FOUND = "使用者不存在"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── Firebase Token 驗證（若前端走 Firebase 登入用） ─────────────────────────────
def verify_firebase_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(AUTH_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    id_token = auth_header.split(" ", 1)[1]
    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        logging.info(f"Firebase token 驗證成功: {decoded_token.get('email')}")
        return decoded_token
    except Exception as e:
        logging.error(f"Firebase token 驗證失敗: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid Firebase token")


# ── 取得目前使用者（支援 Header Bearer token 或 Form token） ──────────────────
def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Form(None)
):
    """
    從 Header 的 Authorization: Bearer user-<uuid>-token 或表單欄位 token 驗證使用者。
    臨時 token 制式：user-<uuid>-token（僅開發用；建議改為正式 JWT）。
    """
    # 1) 優先讀 Header Bearer
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith(AUTH_BEARER_PREFIX):
        token = auth_header.split(" ", 1)[1]

    # 2) 無 token
    if not token:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    # 3) 解析 UUID（只去前後綴）
    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    try:
        _uuid.UUID(user_id)  # 驗證格式
    except Exception:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    # 4) 查 DB
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
    # 1) 先嘗試 Firebase Token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith(AUTH_BEARER_PREFIX):
        id_token = auth_header.split(" ", 1)[1]
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            email_from_token = decoded_token.get("email")
            display_name = decoded_token.get("name") or email_from_token or "User"
            user = db.query(User).filter(User.email == email_from_token).first()
            if not user:
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

    # 2) 沒帶 Firebase Token，走本地帳密
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
    # 取得呼叫者身分
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith(AUTH_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    caller_id_raw = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    try:
        caller_id = int(caller_id_raw)
    except Exception:
        caller_id = caller_id_raw

    caller = db.query(User).filter(User.id == caller_id).first()
    if not caller:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)

    # 目標使用者
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

    return {"id": target.id, "role": target.role}


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    """
    以 Authorization Bearer user-<id>-token 取得當前使用者，回傳基本資料。
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
        "id": user.id,  # 加入 id 欄位供前端通知系統使用
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
        return {"msg": "Firebase 測試成功", "email": test_email}
    except Exception as e:
        return {"msg": "Firebase 測試失敗", "error": str(e)}


# （選用）Google 憑證偵錯：若你未安裝 google-auth，此端點也不會在 import 階段報錯
@router.get("/debug/gcloud")
def debug_gcloud():
    try:
        import google.auth  # 延遲載入，避免無此套件時影響主流程
        creds, project = google.auth.default()
    except Exception as e:
        return {"error": f"google.auth.default() failed: {e}"}

    email = getattr(creds, "service_account_email", None) or getattr(creds, "client_email", None)
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    gac_name = os.path.basename(gac) if gac else None

    return {
        "project": project,
        "credential_type": type(creds).__name__,
        "credential_email": email,
        "GOOGLE_APPLICATION_CREDENTIALS": gac_name,
        "GCS_BUCKET_NAME": os.getenv("GCS_BUCKET_NAME"),
        "UPLOAD_TO_GCS": os.getenv("UPLOAD_TO_GCS"),
    }
