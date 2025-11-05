# app/api/v1/posts.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Any, Dict
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging, json, os, re, uuid as _uuid

# 使用你的 storage.py
from app.services.storage import (
    upload_file_to_gcs_from_bytes,
    delete_file_from_gcs,
    generate_signed_url_from_gcs_uri,
)

from app.core.db import get_db
from app.api.v1.auth import get_current_user

load_dotenv()
logger = logging.getLogger("uvicorn.error")

# 不加 prefix；由 api/v1/router.py 補上 /posts
router = APIRouter(tags=["貼文"], redirect_slashes=False)
security_optional = HTTPBearer(auto_error=False)
security_strict = HTTPBearer(auto_error=False)

# 建議貼文與衣櫃不同 bucket
def _clean_env(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    return v.strip().strip('"').strip("'")

GCS_BUCKET_POST = _clean_env(os.getenv("GCS_BUCKET_POST")) or _clean_env(os.getenv("GCS_BUCKET_NAME")) or "smartclothes_post"
ALLOWED_VISIBILITY = {"public", "friends", "private"}


def current_user_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_strict),
    db: Session = Depends(get_db),
):
    """從 Authorization Bearer 取得當前使用者"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")
    
    token = credentials.credentials
    prefix = "user-"
    suffix = "-token"
    
    # 驗證 token 格式
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail="登入已過期或無效")
    
    # 解析使用者 ID
    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    
    try:
        _uuid.UUID(user_id)  # 驗證 UUID 格式
    except Exception:
        raise HTTPException(status_code=401, detail="登入已過期或無效")
    
    # 查詢資料庫
    from app.models.auth import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    
    return user


def _sanitize_name(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "file"
    return re.sub(r"[^\w\u4e00-\u9fff\-\s]", "_", raw)[:120].strip() or "file"


def _https_from_gcs(gcs_uri: str) -> str:
    # 簽名網址有效時間可調整
    return generate_signed_url_from_gcs_uri(gcs_uri, expiration_minutes=60)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_post(
    file: Optional[UploadFile] = File(None),
    title: str = Form(""),
    content: str = Form(""),
    visibility: str = Form("public"),
    tag: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """
    以單張圖片建立一篇貼文；前端可多次呼叫以多張圖建立多篇貼文。
    （若要一篇含多圖，可再增一支 append-media API）
    """
    try:
        # 檢查是否有文件
        if not file:
            raise HTTPException(status_code=400, detail="必須上傳圖片檔案")
        
        # 讀檔
        await file.seek(0)
        file_bytes = await file.read()
        ext = (Path(file.filename).suffix or ".jpg").lower()
        
        # ✅ 使用貼文標題作為檔名（優先），否則使用原始檔名
        if title and title.strip():
            stem = _sanitize_name(title.strip())
        else:
            stem = _sanitize_name(Path(file.filename).stem or "post")

        # ✅ 處理重複檔名：檢查是否存在，存在則加上 _1, _2, ...
        user_folder = f"posts/{getattr(current_user, 'id', 'unknown')}"
        base_object_name = f"{user_folder}/{stem}{ext}"
        object_name = base_object_name
        
        # 檢查檔案是否存在，如果存在就加上數字後綴
        client = None
        try:
            from google.cloud import storage as gcs_storage
            client = gcs_storage.Client()
            bucket = client.bucket(GCS_BUCKET_POST)
            
            counter = 1
            while bucket.blob(object_name).exists():
                object_name = f"{user_folder}/{stem}_{counter}{ext}"
                counter += 1
                if counter > 100:  # 安全上限，避免無限迴圈
                    logger.warning(f"檔名重複次數過多，使用時間戳: {stem}")
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                    object_name = f"{user_folder}/{stem}_{timestamp}{ext}"
                    break
            
            if counter > 1:
                logger.info(f"檔名重複，使用: {object_name}")
        except Exception as e:
            logger.warning(f"無法檢查檔案是否存在，使用原始檔名: {e}")
            object_name = base_object_name
        
        object_name = object_name.lstrip("/")
        
        # MIME type
        mime = "image/jpeg"
        if ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"

        # 上傳 GCS（私有，前端以簽名網址讀）
        # ❌ 不再支援 SKIP_GCS_UPLOAD，所有圖片必須上傳到 GCS
        try:
            gcs_uri = upload_file_to_gcs_from_bytes(
                file_bytes=file_bytes,
                destination_blob_name=object_name,
                mime_type=mime,
                bucket_name=GCS_BUCKET_POST,
                public=False,
            )
            https_url = _https_from_gcs(gcs_uri)
        except Exception as e:
            logger.exception("GCS upload or signed URL generation failed")
            # 在開發環境回傳詳細錯誤以便除錯；正式環境回傳簡短訊息
            if os.getenv("ENV", "development") == "development":
                raise HTTPException(status_code=500, detail=f"GCS failure: {e}")
            else:
                raise HTTPException(status_code=500, detail="建立貼文失敗（儲存媒體）")

        vis = (visibility or "public").strip().lower()
        if vis not in ALLOWED_VISIBILITY:
            vis = "public"

        # ✅ 資料庫只儲存 gcs_uri (短的 gs:// 格式)
        # url 會在讀取時動態生成
        media_obj = [{
            "type": "image",
            "gcs_uri": gcs_uri,
            "is_cover": True
        }]

        now = datetime.now(timezone.utc)
        sql = text("""
            INSERT INTO user_post
                (user_id, type, title, tag, content, media, visibility, like_count, comment_count, created_at, updated_at)
            VALUES
                (:user_id, :type, :title, :tag, :content, :media, :visibility, :like_count, :comment_count, :created_at, :updated_at)
            RETURNING *;
        """)
        params = {
            "user_id": getattr(current_user, "id", None),
            "type": "post",
            "title": title or "",
            "tag": tag or "",
            "content": content or "",
            "media": json.dumps(media_obj),
            "visibility": vis,
            "like_count": 0,
            "comment_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        row = db.execute(sql, params).mappings().first()
        db.commit()

        item = dict(row or {})
        if "media" in item and isinstance(item["media"], str):
            try:
                media_parsed = json.loads(item["media"])
                for m in media_parsed:
                    if isinstance(m, dict) and str(m.get("gcs_uri", "")).startswith("gs://"):
                        m["url"] = _https_from_gcs(m["gcs_uri"])
                item["media"] = media_parsed
            except Exception:
                pass
        return item or {"message": "貼文已建立"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_post failed")
        raise HTTPException(status_code=500, detail=f"建立貼文失敗: {e}")


@router.get("/")
def list_posts(
    limit: int = 20,
    scope: str = Query("mine", enum=["mine", "all"]),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """列出自己的貼文（一般使用者）或全站（admin 使用 `scope=all`）。"""
    try:
        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if scope == "all" and is_admin:
            sql = text("SELECT * FROM user_post ORDER BY created_at DESC LIMIT :limit")
            params = {"limit": limit}
        else:
            sql = text("SELECT * FROM user_post WHERE user_id = :uid ORDER BY created_at DESC LIMIT :limit")
            params = {"uid": getattr(current_user, "id", None), "limit": limit}

        rows = db.execute(sql, params).mappings().all()
        res: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            try:
                media_parsed = json.loads(item.get("media") or "[]")
                for m in media_parsed:
                    if isinstance(m, dict) and str(m.get("gcs_uri", "")).startswith("gs://"):
                        m["url"] = _https_from_gcs(m["gcs_uri"])
                item["media"] = media_parsed
            except Exception:
                pass
            res.append(item)
        return res
    except Exception:
        logger.exception("list_posts failed")
        raise HTTPException(status_code=500, detail="讀取貼文失敗")


@router.get("/{post_id}")
def get_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """讀取單一貼文。"""
    try:
        row = db.execute(text("SELECT * FROM user_post WHERE id = :id"), {"id": post_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")
        item = dict(row)
        try:
            media_parsed = json.loads(item.get("media") or "[]")
            for m in media_parsed:
                if isinstance(m, dict) and str(m.get("gcs_uri", "")).startswith("gs://"):
                    m["url"] = _https_from_gcs(m["gcs_uri"])
            item["media"] = media_parsed
        except Exception:
            pass
        return item
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_post failed")
        raise HTTPException(status_code=500, detail="讀取貼文失敗")


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """刪除貼文（擁有者或 admin），並嘗試刪除 GCS 物件。"""
    try:
        row = db.execute(text("SELECT * FROM user_post WHERE id = :id"), {"id": post_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if (row["user_id"] != getattr(current_user, "id", None)) and (not is_admin):
            raise HTTPException(status_code=403, detail="無權刪除此貼文")

        # 嘗試刪除 GCS 檔案（失敗不阻斷 DB 刪除）
        try:
            media = json.loads(row.get("media") or "[]")
            for m in media:
                gcs_uri = (m or {}).get("gcs_uri", "")
                if isinstance(gcs_uri, str) and gcs_uri.startswith("gs://"):
                    delete_file_from_gcs(gcs_uri)
        except Exception:
            pass

        db.execute(text("DELETE FROM user_post WHERE id = :id"), {"id": post_id})
        db.commit()
        return
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_post failed")
        raise HTTPException(status_code=500, detail=f"刪除貼文失敗: {e}")
