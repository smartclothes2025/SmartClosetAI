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
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")
    token = credentials.credentials
    try:
        return get_current_user(token=token, db=db)
    except Exception:
        raise HTTPException(status_code=401, detail="登入已過期或無效")


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
        stem = _sanitize_name(Path(file.filename).stem or title or "post")

        # 物件路徑 & MIME
        object_name = f"posts/{getattr(current_user, 'id', 'unknown')}/{stem}{ext}".lstrip("/")
        mime = "image/jpeg"
        if ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"

        # 上傳 GCS（私有，前端以簽名網址讀）
        # 開發時可用 SKIP_GCS_UPLOAD=1 跳過實際上傳（以便在本機測試 UI）
        if os.getenv("SKIP_GCS_UPLOAD", "0") == "1":
            logger.warning("SKIP_GCS_UPLOAD active - not uploading to GCS")
            gcs_uri = f"gs://{GCS_BUCKET_POST}/dev-placeholder.jpg"
            https_url = f"https://storage.googleapis.com/{GCS_BUCKET_POST}/dev-placeholder.jpg"
        else:
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

        media_obj = [{
            "type": "image",
            "gcs_uri": gcs_uri,
            "url": https_url,
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
