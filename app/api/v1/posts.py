# app/api/v1/posts.py
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Depends,
    HTTPException,
    Form,
    status,
    Query,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Any, Dict
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging
import json
import os
import re
import uuid as _uuid
import requests

from app.services.storage import (
    upload_file_to_gcs_from_bytes,
    delete_file_from_gcs,
    generate_signed_url_from_gcs_uri,
)
from app.core.db import get_db

load_dotenv()
logger = logging.getLogger("uvicorn.error")

# 這支 router 由 /api/v1/router.py 加上 /posts prefix
router = APIRouter(tags=["貼文"], redirect_slashes=False)

security_optional = HTTPBearer(auto_error=False)
security_strict = HTTPBearer(auto_error=False)


def _clean_env(v: Optional[str]) -> Optional[str]:
    if not v:
        return v
    return v.strip().strip('"').strip("'")


# 建議貼文與衣櫃不同 bucket
GCS_BUCKET_POST = (
    _clean_env(os.getenv("GCS_BUCKET_POST"))
    or _clean_env(os.getenv("GCS_BUCKET_NAME"))
    or "smartclothes_post"
)

ALLOWED_VISIBILITY = {"public", "friends", "private"}


def current_user_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_strict),
    db: Session = Depends(get_db),
):
    """
    解析 Authorization Bearer，格式預期為：
    Bearer user-<uuid>-token
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")

    token = credentials.credentials
    prefix = "user-"
    suffix = "-token"

    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail="登入已過期或無效")

    user_id = token[len(prefix) : -len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""

    try:
        _uuid.UUID(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="登入已過期或無效")

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
    """由 gs:// 產生簽名網址（貼文圖片仍使用簽名 URL）"""
    return generate_signed_url_from_gcs_uri(gcs_uri, expiration_minutes=60)


# ---------------------------
# 建立貼文（單張圖片）
# ---------------------------
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_post(
    files: List[UploadFile] = File(...),
    title: str = Form(""),
    content: str = Form(""),
    visibility: str = Form("public"),
    tag: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """
    建立一篇貼文，支援多張圖片上傳。
    所有圖片將儲存在同一篇貼文的 media 陣列中。
    """
    try:
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="必須上傳至少一張圖片")

        # 以貼文標題為檔名基礎，沒有就用 "post"
        if title and title.strip():
            stem = _sanitize_name(title.strip())
        else:
            stem = _sanitize_name("post")

        user_folder = f"posts/{getattr(current_user, 'id', 'unknown')}"
        
        # 處理多個檔案上傳
        media_obj = []
        for idx, file in enumerate(files):
            await file.seek(0)
            file_bytes = await file.read()
            ext = (Path(file.filename).suffix or ".jpg").lower()

            # 如果有多個檔案，加上序號
            if len(files) > 1:
                file_stem = f"{stem}_{idx + 1}"
            else:
                file_stem = stem

            base_object_name = f"{user_folder}/{file_stem}{ext}"
            object_name = base_object_name

            # 嘗試避免重覆檔名
            try:
                from google.cloud import storage as gcs_storage

                client = gcs_storage.Client()
                bucket = client.bucket(GCS_BUCKET_POST)
                counter = 1
                while bucket.blob(object_name).exists():
                    object_name = f"{user_folder}/{file_stem}_{counter}{ext}"
                    counter += 1
                    if counter > 100:
                        logger.warning(f"檔名重複次數過多，使用時間戳: {file_stem}")
                        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                        object_name = f"{user_folder}/{file_stem}_{ts}{ext}"
                        break
            except Exception as e:
                logger.warning(f"無法檢查檔案是否存在，使用原始檔名: {e}")
                object_name = base_object_name

            object_name = object_name.lstrip("/")

            mime = "image/jpeg"
            if ext == ".png":
                mime = "image/png"
            elif ext == ".webp":
                mime = "image/webp"

            try:
                gcs_uri = upload_file_to_gcs_from_bytes(
                    file_bytes=file_bytes,
                    destination_blob_name=object_name,
                    mime_type=mime,
                    bucket_name=GCS_BUCKET_POST,
                    public=False,
                )
                
                # 第一張圖片設為封面
                media_obj.append({
                    "type": "image",
                    "gcs_uri": gcs_uri,
                    "is_cover": idx == 0,
                })
            except Exception as e:
                logger.exception(f"GCS upload failed for file {idx + 1}")
                if os.getenv("ENV", "development") == "development":
                    raise HTTPException(status_code=500, detail=f"第 {idx + 1} 張圖片上傳失敗: {e}")
                else:
                    raise HTTPException(status_code=500, detail=f"第 {idx + 1} 張圖片上傳失敗")

        vis = (visibility or "public").strip().lower()
        if vis not in ALLOWED_VISIBILITY:
            vis = "public"

        now = datetime.now(timezone.utc)
        sql = text(
            """
            INSERT INTO user_post
                (user_id, type, title, tag, content, media, visibility,
                 like_count, comment_count, created_at, updated_at)
            VALUES
                (:user_id, :type, :title, :tag, :content, :media, :visibility,
                 :like_count, :comment_count, :created_at, :updated_at)
            RETURNING *;
            """
        )
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


# ---------------------------
# 貼文列表
# ---------------------------
@router.get("/")
def list_posts(
    limit: int = 20,
    scope: str = Query("mine", enum=["mine", "all"]),
    visibility: Optional[str] = Query(None, enum=["public", "friends", "private"]),
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """
    列出貼文：
    - visibility=public：任何人可看（不用登入）
    - scope=mine：登入者自己的貼文
    - scope=all：管理員列出全站貼文
    """
    try:
        if visibility == "public":
            # 公開貼文清單（不用登入）
            sql = text(
                """
                SELECT
                    p.*,
                    u.display_name,
                    u.email,
                    u.picture AS picture
                FROM user_post p
                LEFT JOIN app_users u ON p.user_id = u.id
                WHERE p.visibility = 'public'
                ORDER BY p.created_at DESC
                LIMIT :limit
                """
            )
            params = {"limit": limit}
        else:
            # 需要登入
            if not credentials or not credentials.credentials:
                raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")

            current_user = current_user_from_header(credentials, db)
            role = str(getattr(current_user, "role", "") or "").lower()
            is_admin = role == "admin"

            if scope == "all" and is_admin:
                # 管理員看全站
                if visibility:
                    sql = text(
                        """
                        SELECT
                            p.*,
                            u.display_name,
                            u.email,
                            u.picture AS picture
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.visibility = :visibility
                        ORDER BY p.created_at DESC
                        LIMIT :limit
                        """
                    )
                    params = {"visibility": visibility, "limit": limit}
                else:
                    sql = text(
                        """
                        SELECT
                            p.*,
                            u.display_name,
                            u.email,
                            u.picture AS picture
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        ORDER BY p.created_at DESC
                        LIMIT :limit
                        """
                    )
                    params = {"limit": limit}
            else:
                # 一般使用者看自己的
                if visibility:
                    sql = text(
                        """
                        SELECT
                            p.*,
                            u.display_name,
                            u.email,
                            u.picture AS picture
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.user_id = :uid AND p.visibility = :visibility
                        ORDER BY p.created_at DESC
                        LIMIT :limit
                        """
                    )
                    params = {
                        "uid": getattr(current_user, "id", None),
                        "visibility": visibility,
                        "limit": limit,
                    }
                else:
                    sql = text(
                        """
                        SELECT
                            p.*,
                            u.display_name,
                            u.email,
                            u.picture AS picture
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.user_id = :uid
                        ORDER BY p.created_at DESC
                        LIMIT :limit
                        """
                    )
                    params = {
                        "uid": getattr(current_user, "id", None),
                        "limit": limit,
                    }

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
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_posts failed")
        raise HTTPException(status_code=500, detail="讀取貼文失敗")


# ---------------------------
# 收藏相關
# ---------------------------
def _ensure_favorite_table(db: Session) -> None:
    """在第一次使用時建立 user_post_favorite 表（若不存在）。"""
    try:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_post_favorite (
                    id SERIAL PRIMARY KEY,
                    post_id UUID NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(post_id, user_id)
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_user_post_favorite_user_id
                ON user_post_favorite(user_id);
                """
            )
        )
        db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_user_post_favorite_post_id
                ON user_post_favorite(post_id);
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ensure_favorite_table failed")
        raise HTTPException(status_code=500, detail="初始化收藏表失敗")


@router.post("/{post_id}/favorite")
def toggle_favorite_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """收藏 / 取消收藏貼文（toggle）。"""
    try:
        _ensure_favorite_table(db)

        exists = db.execute(
            text("SELECT 1 FROM user_post WHERE id = :id"), {"id": post_id}
        ).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        user_id = str(getattr(current_user, "id", "") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="找不到使用者資訊")

        existing = db.execute(
            text(
                "SELECT id FROM user_post_favorite WHERE post_id = :pid AND user_id = :uid"
            ),
            {"pid": post_id, "uid": user_id},
        ).mappings().first()

        if existing:
            db.execute(
                text("DELETE FROM user_post_favorite WHERE id = :id"),
                {"id": existing["id"]},
            )
            favorited = False
        else:
            db.execute(
                text(
                    """
                    INSERT INTO user_post_favorite (post_id, user_id)
                    VALUES (:pid, :uid)
                    ON CONFLICT (post_id, user_id) DO NOTHING;
                    """
                ),
                {"pid": post_id, "uid": user_id},
            )
            favorited = True

        db.commit()
        return {"post_id": str(post_id), "favorited": favorited}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("toggle_favorite_post failed")
        raise HTTPException(status_code=500, detail=f"收藏操作失敗: {e}")


@router.get("/favorites/me")
def list_my_favorite_posts(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """列出目前登入使用者收藏的貼文列表。"""
    try:
        _ensure_favorite_table(db)

        user_id = str(getattr(current_user, "id", "") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="找不到使用者資訊")

        sql = text(
            """
            SELECT
                p.*,
                u.display_name,
                u.email,
                u.picture AS picture
            FROM user_post_favorite f
            JOIN user_post p ON f.post_id = p.id
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE f.user_id = :uid
            ORDER BY f.created_at DESC
            LIMIT :limit
            """
        )
        rows = db.execute(sql, {"uid": user_id, "limit": limit}).mappings().all()

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_my_favorite_posts failed")
        raise HTTPException(status_code=500, detail=f"讀取收藏貼文失敗: {e}")


# ---------------------------
# 使用者的公開貼文（Profile 用）
# ---------------------------
@router.get("/user/{user_id}")
def list_user_public_posts(
    user_id: str,
    limit: int = 30,
    db: Session = Depends(get_db),
):
    """列出某位使用者的公開貼文（不需登入）。"""
    try:
        sql = text(
            """
            SELECT
                p.*,
                u.display_name,
                u.email,
                u.interformation,
                u.picture AS picture
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE p.user_id = :uid AND p.visibility = 'public'
            ORDER BY p.created_at DESC
            LIMIT :limit
            """
        )
        rows = db.execute(sql, {"uid": user_id, "limit": limit}).mappings().all()

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
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_user_public_posts failed")
        raise HTTPException(status_code=500, detail="讀取使用者貼文失敗")


# ---------------------------
# 編輯貼文（文字）
# ---------------------------
@router.put("/{post_id}")
def update_post(
    post_id: _uuid.UUID,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """編輯貼文：僅允許擁有者或 admin 更新標題 / 內容 / 標籤 / 可見範圍。"""
    try:
        row = db.execute(
            text("SELECT * FROM user_post WHERE id = :id"),
            {"id": post_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if (row["user_id"] != getattr(current_user, "id", None)) and (not is_admin):
            raise HTTPException(status_code=403, detail="無權編輯此貼文")

        title = (payload.get("title") or row.get("title") or "").strip()
        content = payload.get("content", row.get("content"))
        tag = payload.get("tag", row.get("tag"))

        visibility = (payload.get("visibility") or row.get("visibility") or "public").strip().lower()
        if visibility not in ALLOWED_VISIBILITY:
            visibility = row.get("visibility") or "public"

        updated = db.execute(
            text(
                """
                UPDATE user_post
                SET title = :title,
                    content = :content,
                    tag = :tag,
                    visibility = :visibility,
                    updated_at = NOW()
                WHERE id = :id
                RETURNING id, user_id, title, content, tag, visibility,
                          like_count, comment_count, created_at, updated_at;
                """
            ),
            {
                "id": post_id,
                "title": title,
                "content": content,
                "tag": tag,
                "visibility": visibility,
            },
        ).mappings().first()

        db.commit()
        return dict(updated or {})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("update_post failed")
        raise HTTPException(status_code=500, detail=f"更新貼文失敗: {e}")


# ---------------------------
# 圖片媒體：新增
# ---------------------------
@router.post("/{post_id}/media", status_code=status.HTTP_201_CREATED)
async def append_post_media(
    post_id: _uuid.UUID,
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """將新圖片加入既有貼文的 media 陣列。"""
    try:
        row = db.execute(
            text("SELECT * FROM user_post WHERE id = :id"), {"id": post_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if (row["user_id"] != getattr(current_user, "id", None)) and (not is_admin):
            raise HTTPException(status_code=403, detail="無權修改此貼文")

        media_list = []
        try:
            media_list = json.loads(row.get("media") or "[]")
        except Exception:
            media_list = []

        gcs_uri = None
        if file:
            await file.seek(0)
            file_bytes = await file.read()
            ext = (Path(file.filename).suffix or ".jpg").lower()
            stem = _sanitize_name(Path(file.filename).stem or "media")
            user_folder = f"posts/{getattr(current_user, 'id', 'unknown')}/{post_id}"
            object_name = f"{user_folder}/{stem}{ext}".lstrip("/")

            try:
                gcs_uri = upload_file_to_gcs_from_bytes(
                    file_bytes=file_bytes,
                    destination_blob_name=object_name,
                    mime_type=("image/png" if ext == ".png" else "image/jpeg"),
                    bucket_name=GCS_BUCKET_POST,
                    public=False,
                )
            except Exception as e:
                logger.exception("upload file to gcs failed")
                raise HTTPException(status_code=500, detail=f"媒體上傳失敗: {e}")
        elif image_url:
            image_url = image_url.strip()
            if image_url.startswith("gs://"):
                gcs_uri = image_url
            else:
                try:
                    resp = requests.get(image_url, timeout=15)
                    if resp.status_code != 200:
                        raise Exception(f"HTTP {resp.status_code}")
                    file_bytes = resp.content
                    ext = ".jpg"
                    user_folder = f"posts/{getattr(current_user, 'id', 'unknown')}/{post_id}"
                    object_name = (
                        f"{user_folder}/{_sanitize_name(Path(image_url).stem or 'media')}{ext}"
                    ).lstrip("/")
                    gcs_uri = upload_file_to_gcs_from_bytes(
                        file_bytes=file_bytes,
                        destination_blob_name=object_name,
                        mime_type="image/jpeg",
                        bucket_name=GCS_BUCKET_POST,
                        public=False,
                    )
                except Exception as e:
                    logger.exception("download or upload external image failed")
                    raise HTTPException(
                        status_code=400, detail=f"無法處理提供的 image_url: {e}"
                    )
        else:
            raise HTTPException(status_code=400, detail="必須提供上傳檔案或 image_url")

        if gcs_uri:
            new_media = {"type": "image", "gcs_uri": gcs_uri, "is_cover": False}
            media_list.append(new_media)

            try:
                result = db.execute(
                    text(
                        "UPDATE user_post SET media = :media, updated_at = NOW() "
                        "WHERE id = :id RETURNING media"
                    ),
                    {"media": json.dumps(media_list), "id": post_id},
                ).mappings().first()
                db.commit()
            except Exception:
                db.rollback()
                raise

            updated_media = []
            try:
                updated_media = json.loads(result.get("media") or "[]") if result else media_list
            except Exception:
                updated_media = media_list

            for m in updated_media:
                if isinstance(m, dict) and str(m.get("gcs_uri", "")).startswith("gs://"):
                    m["url"] = _https_from_gcs(m["gcs_uri"])

            return {"post_id": str(post_id), "media": updated_media}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("append_post_media failed")
        raise HTTPException(status_code=500, detail=f"新增媒體失敗: {e}")


# ---------------------------
# 圖片媒體：刪除
# ---------------------------
@router.delete("/{post_id}/media")
def delete_post_media(
    post_id: _uuid.UUID,
    gcs_uri: str = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """從貼文中刪除指定的媒體（by gcs_uri），並嘗試刪除 GCS 物件。"""
    try:
        row = db.execute(
            text("SELECT * FROM user_post WHERE id = :id"), {"id": post_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if (row["user_id"] != getattr(current_user, "id", None)) and (not is_admin):
            raise HTTPException(status_code=403, detail="無權修改此貼文")

        try:
            media_list = json.loads(row.get("media") or "[]")
        except Exception:
            media_list = []

        found = False
        new_media = []
        for m in media_list:
            if isinstance(m, dict) and str(m.get("gcs_uri", "")) == gcs_uri:
                found = True
                try:
                    if isinstance(gcs_uri, str) and gcs_uri.startswith("gs://"):
                        delete_file_from_gcs(gcs_uri)
                except Exception:
                    logger.warning(f"failed to delete gcs object: {gcs_uri}")
                continue
            new_media.append(m)

        if not found:
            raise HTTPException(status_code=404, detail="找不到指定的媒體項目")

        try:
            result = db.execute(
                text(
                    "UPDATE user_post SET media = :media, updated_at = NOW() "
                    "WHERE id = :id RETURNING media"
                ),
                {"media": json.dumps(new_media), "id": post_id},
            ).mappings().first()
            db.commit()
        except Exception:
            db.rollback()
            raise

        updated_media = []
        try:
            updated_media = json.loads(result.get("media") or "[]") if result else new_media
        except Exception:
            updated_media = new_media

        for m in updated_media:
            if isinstance(m, dict) and str(m.get("gcs_uri", "")).startswith("gs://"):
                m["url"] = _https_from_gcs(m["gcs_uri"])

        return {"post_id": str(post_id), "media": updated_media}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("delete_post_media failed")
        raise HTTPException(status_code=500, detail=f"刪除媒體失敗: {e}")


# ---------------------------
# 按讚（toggle）
# ---------------------------
@router.post("/{post_id}/like")
def like_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """
    對貼文按讚 / 收回愛心（toggle）。
    回傳：post_id, like_count, liked
    """

    def _ensure_like_table(inner_db: Session) -> None:
        try:
            inner_db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS user_post_like (
                        id SERIAL PRIMARY KEY,
                        post_id UUID NOT NULL,
                        user_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(post_id, user_id)
                    );
                    """
                )
            )
            inner_db.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_post_like_post_id
                    ON user_post_like(post_id);
                    """
                )
            )
            inner_db.commit()
        except Exception:
            inner_db.rollback()
            logger.exception("ensure_like_table failed")
            raise HTTPException(status_code=500, detail="初始化按讚表失敗")

    try:
        _ensure_like_table(db)

        row = db.execute(
            text("SELECT like_count FROM user_post WHERE id = :id"),
            {"id": post_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        user_id = str(getattr(current_user, "id", "") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="找不到使用者資訊")

        existing = db.execute(
            text(
                "SELECT id FROM user_post_like WHERE post_id = :pid AND user_id = :uid"
            ),
            {"pid": post_id, "uid": user_id},
        ).mappings().first()

        if existing:
            db.execute(
                text("DELETE FROM user_post_like WHERE id = :id"),
                {"id": existing["id"]},
            )
            updated = db.execute(
                text(
                    """
                    UPDATE user_post
                    SET like_count = GREATEST(COALESCE(like_count, 0) - 1, 0),
                        updated_at = NOW()
                    WHERE id = :id
                    RETURNING like_count;
                    """
                ),
                {"id": post_id},
            ).mappings().first()
            liked = False
        else:
            db.execute(
                text(
                    """
                    INSERT INTO user_post_like (post_id, user_id)
                    VALUES (:pid, :uid)
                    ON CONFLICT (post_id, user_id) DO NOTHING;
                    """
                ),
                {"pid": post_id, "uid": user_id},
            )
            updated = db.execute(
                text(
                    """
                    UPDATE user_post
                    SET like_count = COALESCE(like_count, 0) + 1,
                        updated_at = NOW()
                    WHERE id = :id
                    RETURNING like_count;
                    """
                ),
                {"id": post_id},
            ).mappings().first()
            liked = True

        db.commit()
        return {
            "post_id": str(post_id),
            "like_count": updated["like_count"],
            "liked": liked,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("like_post failed")
        raise HTTPException(status_code=500, detail=f"按讚失敗: {e}")


# ---------------------------
# 讀取單一貼文（含作者頭貼）
# ---------------------------
@router.get("/{post_id}")
def get_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """讀取單一貼文，附帶作者 display_name / picture 與 liked_by_me。"""
    try:
        sql = text(
            """
            SELECT
                p.*,
                u.display_name,
                u.email,
                u.picture AS picture
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE p.id = :id
            """
        )
        row = db.execute(sql, {"id": post_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        item = dict(row)

        # 判斷目前使用者是否已按讚
        liked_by_me = False
        if credentials and credentials.credentials:
            try:
                current_user = current_user_from_header(credentials, db)
                user_id = str(getattr(current_user, "id", "") or "")
                if user_id:
                    like_exists = db.execute(
                        text(
                            "SELECT 1 FROM user_post_like WHERE post_id = :pid AND user_id = :uid"
                        ),
                        {"pid": post_id, "uid": user_id},
                    ).scalar()
                    liked_by_me = bool(like_exists)
            except HTTPException:
                liked_by_me = False
            except Exception:
                logger.exception("get_post liked_by_me check failed")
        item["liked_by_me"] = liked_by_me

        # 補上 nested user 物件，給前端方便使用（同時保留平面欄位）
        item["user"] = {
            "id": item.get("user_id"),
            "display_name": item.get("display_name"),
            "email": item.get("email"),
            "picture": item.get("picture"),
        }

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


# ---------------------------
# 留言：確保資料表存在
# ---------------------------
def _ensure_comment_table(db: Session) -> None:
    """
    確保 user_post_comment 表存在且欄位齊全。
    若是舊表（沒有 user_display_name / user_picture），會自動補欄位。
    """
    try:
        # 1. 最小結構（舊環境可能只有 id / post_id / content / created_at）
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_post_comment (
                    id SERIAL PRIMARY KEY,
                    post_id UUID NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        # 2. 補欄位（若已存在則略過）
        db.execute(
            text(
                """
                ALTER TABLE user_post_comment
                ADD COLUMN IF NOT EXISTS user_display_name TEXT;
                """
            )
        )
        db.execute(
            text(
                """
                ALTER TABLE user_post_comment
                ADD COLUMN IF NOT EXISTS user_picture TEXT;
                """
            )
        )
        # 3. 索引
        db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_user_post_comment_post_id
                ON user_post_comment(post_id);
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ensure_comment_table failed")
        raise HTTPException(status_code=500, detail="初始化留言表失敗")


# ---------------------------
# 留言：列表
# ---------------------------
@router.get("/{post_id}/comments")
def list_post_comments(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
):
    """取得指定貼文的留言列表。"""
    try:
        _ensure_comment_table(db)

        rows = (
            db.execute(
                text(
                    """
                    SELECT id, content, created_at,
                           user_display_name, user_picture
                    FROM user_post_comment
                    WHERE post_id = :pid
                    ORDER BY created_at DESC
                    """
                ),
                {"pid": post_id},
            )
            .mappings()
            .all()
        )

        comments: List[Dict[str, Any]] = []
        for r in rows:
            comments.append(
                {
                    "id": r["id"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "user": {
                        "display_name": r.get("user_display_name"),
                        "picture": r.get("user_picture"),
                    },
                }
            )
        return comments
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("list_post_comments failed")
        raise HTTPException(status_code=500, detail=f"讀取留言失敗: {e}")


# ---------------------------
# 留言：新增
# ---------------------------
@router.post("/{post_id}/comments")
def create_post_comment(
    post_id: _uuid.UUID,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """新增一則留言並回傳留言內容。"""
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="留言內容不得為空")

    try:
        _ensure_comment_table(db)

        exists = db.execute(
            text("SELECT 1 FROM user_post WHERE id = :id"), {"id": post_id}
        ).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        row = (
            db.execute(
                text(
                    """
                    INSERT INTO user_post_comment
                        (post_id, user_display_name, user_picture, content, created_at)
                    VALUES
                        (:pid, :uname, :upic, :content, NOW())
                    RETURNING id, post_id, user_display_name, user_picture, content, created_at;
                    """
                ),
                {
                    "pid": post_id,
                    "uname": getattr(current_user, "display_name", None)
                    or getattr(current_user, "email", None),
                    "upic": getattr(current_user, "picture", None),
                    "content": content,
                },
            )
            .mappings()
            .first()
        )

        db.execute(
            text(
                """
                UPDATE user_post
                SET comment_count = COALESCE(comment_count, 0) + 1,
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": post_id},
        )

        db.commit()

        result = {
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"],
            "user": {
                "display_name": row.get("user_display_name")
                or getattr(current_user, "display_name", None)
                or getattr(current_user, "email", None),
                "picture": row.get("user_picture")
                or getattr(current_user, "picture", None),
            },
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("create_post_comment failed")
        raise HTTPException(status_code=500, detail=f"留言失敗: {e}")


# ---------------------------
# 刪除貼文
# ---------------------------
@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """刪除貼文（擁有者或 admin），並嘗試刪除 GCS 物件。"""
    try:
        row = db.execute(
            text("SELECT * FROM user_post WHERE id = :id"), {"id": post_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        role = str(getattr(current_user, "role", "") or "").lower()
        is_admin = role == "admin"
        if (row["user_id"] != getattr(current_user, "id", None)) and (not is_admin):
            raise HTTPException(status_code=403, detail="無權刪除此貼文")

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
