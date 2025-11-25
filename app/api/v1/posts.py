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
    visibility: Optional[str] = Query(None, enum=["public", "friends", "private"]),
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """
    列出貼文。
    - scope=mine: 只列出自己的貼文（需要登入）
    - scope=all: 列出全站貼文（admin 專用，需要登入）
    - visibility=public: 列出所有公開貼文（不需要登入）
    """
    try:
        # ✅ 如果指定 visibility=public，不需要登入即可查看
        if visibility == "public":
            sql = text("""
                SELECT 
                    p.*,
                    u.display_name,
                    u.email,
                    u.avatar_url
                FROM user_post p
                LEFT JOIN app_users u ON p.user_id = u.id
                WHERE p.visibility = 'public' 
                ORDER BY p.created_at DESC 
                LIMIT :limit
            """)
            params = {"limit": limit}
        else:
            # 需要登入的情況
            if not credentials or not credentials.credentials:
                raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")
            
            current_user = current_user_from_header(credentials, db)
            role = str(getattr(current_user, "role", "") or "").lower()
            is_admin = role == "admin"
            
            if scope == "all" and is_admin:
                # Admin 查看全站
                if visibility:
                    sql = text("""
                        SELECT 
                            p.*,
                            u.display_name,
                            u.email,
                            u.avatar_url
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.visibility = :visibility 
                        ORDER BY p.created_at DESC 
                        LIMIT :limit
                    """)
                    params = {"visibility": visibility, "limit": limit}
                else:
                    sql = text("""
                        SELECT 
                            p.*,
                            u.display_name,
                            u.email,
                            u.avatar_url
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        ORDER BY p.created_at DESC 
                        LIMIT :limit
                    """)
                    params = {"limit": limit}
            else:
                # 一般使用者查看自己的貼文
                if visibility:
                    sql = text("""
                        SELECT 
                            p.*,
                            u.display_name,
                            u.email,
                            u.avatar_url
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.user_id = :uid AND p.visibility = :visibility 
                        ORDER BY p.created_at DESC 
                        LIMIT :limit
                    """)
                    params = {"uid": getattr(current_user, "id", None), "visibility": visibility, "limit": limit}
                else:
                    sql = text("""
                        SELECT 
                            p.*,
                            u.display_name,
                            u.email,
                            u.avatar_url
                        FROM user_post p
                        LEFT JOIN app_users u ON p.user_id = u.id
                        WHERE p.user_id = :uid 
                        ORDER BY p.created_at DESC 
                        LIMIT :limit
                    """)
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_posts failed")
        raise HTTPException(status_code=500, detail="讀取貼文失敗")


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

        # 確認貼文存在
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
                u.avatar_url
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
                u.avatar_url
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


@router.post("/{post_id}/like")
def like_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_from_header),
):
    """對貼文按讚 / 收回愛心（toggle）。

    - 若目前尚未按讚：新增一筆 user_post_like 紀錄，like_count +1。
    - 若已按讚：刪除該紀錄，like_count -1（不少於 0）。
    回傳最新的 like_count 與 liked 狀態。
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

        # 先確認貼文存在
        row = db.execute(
            text("SELECT like_count FROM user_post WHERE id = :id"),
            {"id": post_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        user_id = str(getattr(current_user, "id", "") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="找不到使用者資訊")

        # 檢查是否已經按讚
        existing = db.execute(
            text(
                "SELECT id FROM user_post_like WHERE post_id = :pid AND user_id = :uid"
            ),
            {"pid": post_id, "uid": user_id},
        ).mappings().first()

        if existing:
            # 已按讚 → 收回愛心
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
            # 尚未按讚 → 新增一筆紀錄
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

@router.get("/{post_id}")
def get_post(
    post_id: _uuid.UUID,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """讀取單一貼文。"""
    try:
        # ✅ 加入 JOIN 查詢，同時獲取使用者資訊
        sql = text("""
            SELECT 
                p.*,
                u.display_name,
                u.email,
                u.avatar_url
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE p.id = :id
        """)
        row = db.execute(sql, {"id": post_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="找不到該貼文")
        item = dict(row)

        # 判斷目前使用者是否已按讚（liked_by_me）
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


def _ensure_comment_table(db: Session) -> None:
    """在第一次使用時建立 user_post_comment 表（若不存在）。"""
    try:
        # 不使用外鍵，避免不同環境下 user_post / app_users schema 差異導致錯誤
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_post_comment (
                    id SERIAL PRIMARY KEY,
                    post_id UUID NOT NULL,
                    user_display_name TEXT,
                    user_picture TEXT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_user_post_comment_post_id
                ON user_post_comment(post_id);
                """
            )
        )
        # 若是先前建立的舊表，補上缺少的欄位避免 SELECT 失敗
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
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ensure_comment_table failed")
        raise HTTPException(status_code=500, detail="初始化留言表失敗")


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

        # 確認貼文存在
        exists = db.execute(
            text("SELECT 1 FROM user_post WHERE id = :id"), {"id": post_id}
        ).scalar()
        if not exists:
            raise HTTPException(status_code=404, detail="找不到該貼文")

        row = (
            db.execute(
                text(
                    """
                    INSERT INTO user_post_comment (post_id, user_display_name, user_picture, content, created_at)
                    VALUES (:pid, :uname, :upic, :content, NOW())
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

        # 更新貼文的留言數
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

# 直接貼到 app/api/v1/posts.py 裡（放在 get_post 後面即可）
