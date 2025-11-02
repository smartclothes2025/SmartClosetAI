# app/api/v1/clothes.py
# -*- coding: utf-8 -*-

from fastapi import (
    APIRouter, UploadFile, File, Depends, HTTPException, Form, status, Body, Request
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel
import shutil
import re
import logging
import json
import os

from app.core.db import get_db
from app.models.wardrobe import WardrobeItem, CategoryEnum
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.services.image_processing import process_image, analyze_clothing_type
from app.services.storage import (
    upload_file_to_gcs,
    delete_file_from_gcs,
    generate_signed_url_from_gcs_uri,
    is_gcs_like_url,
)

# -----------------------------------------------------------------------------
# 設定 / 常數
# -----------------------------------------------------------------------------
router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

security_optional = HTTPBearer(auto_error=False)

# 是否啟用 GCS（從環境變數讀取）
USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

# 前端英文值到資料庫中文值的映射
CATEGORY_MAP = {
    "tops": "上衣",
    "skirts": "裙子",
    "pants": "褲子",
    "dresses": "洋裝",
    "outerwear": "外套",
    "shoes": "鞋子",
    "hats": "帽子",
    "bags": "包包",
    "accessories": "配件",
    "bottoms": "褲子",
        "socks": "襪子",  # Add mapping for socks
    # 已是中文者原樣通過
    "上衣": "上衣",
    "裙子": "裙子",
    "褲子": "褲子",
    "洋裝": "洋裝",
    "外套": "外套",
    "鞋子": "鞋子",
    "帽子": "帽子",
    "包包": "包包",
    "配件": "配件",
}


# -----------------------------------------------------------------------------
# 工具函式
# -----------------------------------------------------------------------------
def resolve_image_url(uri: str) -> str:
    """將 DB 中的圖片 URI 轉成可直接存取的 URL（gs:// → 簽名網址；其他原樣返回）"""
    if not uri:
        return ""
    if uri.startswith("gs://"):
        try:
            return generate_signed_url_from_gcs_uri(uri, expiration_minutes=60)
        except Exception as e:
            logger.warning(f"無法產生 GCS 簽署 URL: {e}")
            return ""
    return uri


def _sanitize_name(raw: str) -> str:
    """清理檔名為安全字元"""
    raw = (raw or "").strip()
    if not raw:
        return "file"
    return re.sub(r"[^\w\u4e00-\u9fff\-\s]", "_", raw)[:120].strip() or "file"


async def _get_optional_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[User]:
    """
    可選的使用者認證（允許訪客）。配合簡易 token：Bearer user-<id>-token
    """
    if not credentials:
        return None

    token = credentials.credentials
    prefix, suffix = "user-", "-token"

    if isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix):
        raw_id = token[len(prefix) : -len(suffix)]
        try:
            parsed_id = int(raw_id)
        except Exception:
            parsed_id = raw_id
        return db.query(User).filter(User.id == parsed_id).first()

    return None


# -----------------------------------------------------------------------------
# Pydantic 請求模型
# -----------------------------------------------------------------------------
class ClothesUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    tags: Optional[List[str]] = None
    attributes: Optional[Dict[str, Any]] = None
    style: Optional[str] = None
    brand: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "白色T恤",
                "category": "上衣",
                "color": "白色",
                "style": "休閒",
                "tags": ["夏季", "基本款"],
                "attributes": {"brand": "Uniqlo", "size": "M"},
            }
        }


# -----------------------------------------------------------------------------
# 路由：上傳衣物
# -----------------------------------------------------------------------------
@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_clothes(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form("上衣"),
    color: str = Form(""),
    tags: str = Form("[]"),
    attributes: str = Form("{}"),
    style: str = Form("休閒"),
    remove_bg: str = Form("0"),
    ai_detect: str = Form("0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上傳衣物圖片（支援去背、AI 辨識、GCS 儲存）"""
    temp_file_path: Optional[Path] = None
    processed_file_path: Optional[Path] = None
    final_file_path: Optional[Path] = None

    try:
        # 1) 解析參數
        tags_list = json.loads(tags) if tags else []
        attributes_dict = json.loads(attributes) if attributes else {}
        ai_detect_enabled = ai_detect == "1"
        remove_bg_enabled = remove_bg == "1"

        # 類別英文→中文
        category = CATEGORY_MAP.get(category.strip(), category.strip()) or "上衣"
        logger.info(f"收到 category: {category}")

        # 2) 儲存原始檔
        safe_stem = _sanitize_name(name) if name.strip() else _sanitize_name(Path(file.filename).stem)
        orig_ext = Path(file.filename).suffix or ".jpg"

        temp_dir = UPLOAD_ROOT / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_name = f"{safe_stem}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_temp{orig_ext}"
        temp_file_path = temp_dir / temp_file_name

        with open(temp_file_path, "wb") as out:
            file.file.seek(0)
            shutil.copyfileobj(file.file, out)

        final_file_path = temp_file_path

        # 3) 去背
        if remove_bg_enabled:
            logger.info(f"執行去背: {final_file_path}")
            proc_res = process_image(str(final_file_path))
            processed_file_path = Path(proc_res["processed_image_path"])
            final_file_path = processed_file_path

        # 4) AI 辨識
        if ai_detect_enabled:
            logger.info(f"執行 AI 辨識: {final_file_path}")
            analysis_result = analyze_clothing_type(str(final_file_path), ai_detect_enabled=True)
            if analysis_result.get("category") and analysis_result["category"] != "特殊":
                category = analysis_result["category"]
            if analysis_result.get("colors"):
                color = analysis_result["colors"][0]
            if analysis_result.get("style"):
                style = analysis_result["style"]

        # 5) 轉換為枚舉
        try:
            cat_enum = CategoryEnum(category) if category in [e.value for e in CategoryEnum] else CategoryEnum.TOP
        except Exception:
            cat_enum = CategoryEnum.TOP

        # 6) 實際存檔（GCS 或本地）
        if USE_GCS and GCS_BUCKET_NAME:
            safe_cat = category.strip().replace("/", "_")
            # 依你專案結構：wardrobe/wardrobe_items.<user_id>/<類別>/<檔名>
            gcs_path = f"wardrobe/wardrobe_items.{current_user.id}/{safe_cat}/{safe_stem}{final_file_path.suffix}"

            with open(final_file_path, "rb") as f:
                file_bytes = f.read()

            ext = final_file_path.suffix.lower()
            if ext == ".png":
                mime_type = "image/png"
            elif ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif ext == ".webp":
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"

            logger.info(f"上傳至 GCS: {gcs_path}")
            gcs_url = upload_file_to_gcs(
                file_bytes=file_bytes,
                destination_blob_name=gcs_path,
                mime_type=mime_type,
                bucket_name=GCS_BUCKET_NAME,
                public=False,
            )
            # DB 建議統一存 gs://...
            cover_url = gcs_url
            logger.info(f"GCS URL: {cover_url}")
        else:
            safe_cat = category.strip().replace("/", "_")
            dest_dir = UPLOAD_ROOT / safe_cat
            dest_dir.mkdir(parents=True, exist_ok=True)

            final_ext = final_file_path.suffix
            candidate = f"{safe_stem}{final_ext}"
            save_path = dest_dir / candidate

            if save_path.exists():
                stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                candidate = f"{safe_stem}_{stamp}{final_ext}"
                save_path = dest_dir / candidate

            shutil.move(str(final_file_path), str(save_path))
            cover_url = f"/uploads/{safe_cat}/{candidate}"

        # 7) 建立 DB 記錄
        item = WardrobeItem(
            user_id=current_user.id,
            name=name or safe_stem,
            category=cat_enum,
            color=color or "",
            cover_image_url=cover_url,  # DB 儲存 gs:// 或 /uploads/...
            tags=tags_list,
            attributes=attributes_dict,
            brand=attributes_dict.get("brand", ""),
            style=style if style else None,
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        # 回傳前統一處理 URL
        resolved_url = resolve_image_url(item.cover_image_url)

        return {
            "message": "上傳成功",
            "item": {
                "id": str(item.id),
                "name": item.name,
                "category": item.category.value,
                "color": item.color,
                "img": resolved_url,
                "daysInactive": None,
                "owner_display_name": item.user.display_name if item.user else "",
                "last_worn_at": item.last_worn_at.isoformat() if item.last_worn_at else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("上傳失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"上傳失敗: {str(e)}")
    finally:
        # 清理臨時檔案
        for path in (temp_file_path, processed_file_path):
            if path and path.exists():
                try:
                    os.unlink(path)
                    logger.debug(f"已刪除臨時檔案: {path}")
                except Exception as ex:
                    logger.warning(f"無法刪除臨時檔案 {path}: {ex}")


# -----------------------------------------------------------------------------
# 路由：列出衣物
# -----------------------------------------------------------------------------
@router.get("/")
def list_clothes(
    limit: int = 50,
    scope: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(_get_optional_current_user),
):
    """取得衣櫃清單"""
    try:
        # 訪客檢查
        if user and (user.id == 99 or user.email == "guest@local"):
            return []

        q = db.query(WardrobeItem)

        is_admin = user and getattr(user, "role", None) == "admin"
        if scope == "all" and is_admin:
            logger.info(f"管理者 {user.id} 請求所有衣物")
        elif user:
            q = q.filter(WardrobeItem.user_id == user.id)

        q = q.order_by(WardrobeItem.created_at.desc()).limit(limit)
        rows = q.all()

        result: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for item in rows:
            img_url = resolve_image_url(item.cover_image_url)
            logger.info(f"Item ID {item.id}: DB-URI='{item.cover_image_url}', Resolved-URL='{img_url}'")

            dt = item.updated_at or item.created_at
            days = None
            if dt:
                base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                days = (now - base).days

            result.append(
                {
                    "id": str(item.id),
                    "name": item.name or "",
                    "category": item.category.value if item.category else "",
                    "color": item.color or "",
                    "img": img_url,
                    "daysInactive": days,
                    "owner_display_name": item.user.display_name if item.user else "",
                    "user_id": item.user_id,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
            )

        return result

    except Exception:
        logger.exception("取得衣櫃清單失敗")
        raise HTTPException(status_code=500, detail="讀取衣櫃失敗")


# -----------------------------------------------------------------------------
# 路由：單筆衣物
# -----------------------------------------------------------------------------
@router.get("/{item_id}")
def get_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
):
    """取得單一衣物詳情"""
    try:
        try:
            parsed_id = int(item_id)
        except Exception:
            parsed_id = item_id

        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")

        img_url = resolve_image_url(item.cover_image_url)

        dt = item.updated_at or item.created_at
        days = None
        now = datetime.now(timezone.utc)
        if dt:
            base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            days = (now - base).days

        return {
            "id": str(item.id),
            "name": item.name or "",
            "category": item.category.value if item.category else "",
            "color": item.color or "",
            "img": img_url,
            "daysInactive": days,
            "owner_display_name": item.user.display_name if item.user else "",
            "tags": item.tags or [],
            "attributes": item.attributes or {},
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("取得衣物詳情失敗")
        raise HTTPException(status_code=500, detail="讀取衣物失敗")


# -----------------------------------------------------------------------------
# 路由：更新衣物
# -----------------------------------------------------------------------------
@router.patch("/{item_id}")
@router.put("/{item_id}")
async def update_clothes_item(
    item_id: str,
    request: Request,
    body: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新衣物資訊（支援部分更新，接受 JSON）"""
    try:
        logger.info(f"收到更新請求 - item_id: {item_id}")
        logger.info(f"原始 request body: {body}")

        # 支援 { "payload": {...} } 或直接 {...}
        data = None
        if isinstance(body, dict):
            data = body.get("payload", body)

        if data is None:
            try:
                raw = await request.json()
                if isinstance(raw, dict):
                    data = raw.get("payload", raw)
            except Exception as ex:
                logger.debug(f"無法從 request.json() 取得 body: {ex}")

        if data is None:
            raise HTTPException(status_code=422, detail="缺少 request body 或 payload")

        # Pydantic 驗證
        try:
            payload = ClothesUpdateRequest.model_validate(data)
        except Exception as e:
            logger.warning(f"無法解析更新資料: {e}")
            raise HTTPException(status_code=422, detail=f"資料驗證失敗: {str(e)}")

        logger.info(f"更新資料 (validated): {payload.model_dump(exclude_none=True)}")

        # 欄位取出
        name = payload.name
        category = payload.category
        color = payload.color
        tags = payload.tags
        attributes = payload.attributes
        style = payload.style
        brand = payload.brand

        # 解析 ID 與查詢
        try:
            parsed_id = int(item_id)
        except Exception:
            parsed_id = item_id

        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")

        # 權限
        is_admin = getattr(current_user, "role", None) == "admin"
        if not is_admin and item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限編輯此衣物")

        if is_admin and item.user_id != current_user.id:
            logger.info(f"管理員 {current_user.id} 編輯了使用者 {item.user_id} 的衣物 {item_id}")

        # 實際更新（僅更新有提供者）
        if name is not None:
            item.name = name

        if category is not None:
            mapped = CATEGORY_MAP.get(category.strip(), category.strip())
            try:
                cat_enum = CategoryEnum(mapped) if mapped in [e.value for e in CategoryEnum] else None
                if cat_enum:
                    item.category = cat_enum
            except Exception as ex:
                logger.warning(f"無效的 category: {category}, 錯誤: {ex}")

        if color is not None:
            item.color = color

        if style is not None:
            # 嘗試查詢 enum 允許值
            try:
                enum_name = "style_enum"
                rows = db.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum "
                        "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                        "WHERE pg_type.typname = :name"
                    ),
                    {"name": enum_name},
                ).fetchall()
                allowed_values = [r[0] for r in rows]
            except Exception as _e:
                allowed_values = None
                logger.debug(f"無法查詢 enum 值: {_e}")

            if allowed_values:
                if style in allowed_values:
                    item.style = style
                else:
                    logger.warning(f"未知的 style 值，跳過更新: {style}; 允許: {allowed_values}")
            else:
                item.style = style  # 保守策略

        if brand is not None:
            item.brand = brand

        if tags is not None:
            item.tags = tags

        if attributes is not None:
            item.attributes = attributes

        item.updated_at = datetime.now(timezone.utc)

        try:
            db.commit()
        except Exception as commit_error:
            logger.error(f"db.commit() 失敗: {commit_error}")
            db.rollback()
            raise

        try:
            db.refresh(item)
        except Exception as refresh_error:
            logger.error(f"db.refresh() 失敗: {refresh_error}")

        # 回傳
        img_url = resolve_image_url(item.cover_image_url)
        now = datetime.now(timezone.utc)
        dt = item.updated_at or item.created_at
        days = None
        if dt:
            base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            days = (now - base).days

        return {
            "message": "更新成功",
            "item": {
                "id": str(item.id),
                "name": item.name or "",
                "category": item.category.value if item.category else "",
                "color": item.color or "",
                "img": img_url,
                "daysInactive": days,
                "owner_display_name": item.user.display_name if item.user else "",
                "tags": item.tags or [],
                "attributes": item.attributes or {},
                "style": item.style or "",
                "brand": item.brand or "",
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新衣物失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失敗: {str(e)}")


# -----------------------------------------------------------------------------
# 路由：刪除衣物（會同時刪除圖檔）
# -----------------------------------------------------------------------------
@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """刪除衣物（管理員可刪除所有使用者的衣物）；先刪檔後刪 DB。"""
    try:
        try:
            parsed_id = int(item_id)
        except Exception:
            parsed_id = item_id

        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")

        is_admin = getattr(current_user, "role", None) == "admin"
        if not is_admin and item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限刪除此衣物")

        if is_admin and item.user_id != current_user.id:
            logger.info(f"管理員 {current_user.id} 刪除了使用者 {item.user_id} 的衣物 {item_id}")

        # --- 先刪除圖片 ---
        img_uri = item.cover_image_url
        deleted_remote = True  # 預設當成功（若沒有圖片也不阻擋）

        if img_uri and isinstance(img_uri, str):
            # 1) 本地檔案：/uploads/...
            if img_uri.startswith("/uploads/"):
                relative_path = Path(img_uri.lstrip("/"))
                abs_path = (UPLOAD_ROOT.parent / relative_path).resolve()

                # 僅允許刪除 uploads 目錄底下的檔案
                uploads_root = (UPLOAD_ROOT.parent / "uploads").resolve()
                if str(abs_path).startswith(str(uploads_root)):
                    try:
                        if abs_path.exists():
                            abs_path.unlink()
                            logger.info(f"已刪除本地圖片: {abs_path}")
                        else:
                            logger.warning(f"刪除本地圖片：檔案不存在（視為成功） {abs_path}")
                    except Exception as ex:
                        logger.warning(f"刪除本地圖片時發生錯誤: {ex}")
                        deleted_remote = False

            # 2) GCS 物件（gs://、storage.googleapis.com、storage.cloud.google.com、firebase、gcs/<bucket>/...）
            elif is_gcs_like_url(img_uri):
                try:
                    ok = delete_file_from_gcs(img_uri, bucket_name=GCS_BUCKET_NAME or None)
                    deleted_remote = ok
                    if ok:
                        logger.info(f"已刪除或不存在（視為成功）：{img_uri}")
                    else:
                        logger.warning(f"GCS 圖片刪除失敗（權限/解析/連線）：{img_uri}")
                except Exception as ex:
                    logger.warning(f"GCS 刪除例外：{ex}")
                    deleted_remote = False

            # 3) 其他外部 URL：忽略
            else:
                logger.info(f"衣物圖片為外部 URL，跳過刪除: {img_uri}")

        # --- 再刪除 DB 記錄 ---
        db.delete(item)
        db.commit()

        # 若檔案刪除失敗，仍回 204，但在日誌提醒
        if not deleted_remote:
            logger.warning(f"衣物 {item_id} DB 已刪，但圖檔刪除可能失敗，請檢查權限/路徑。")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("刪除衣物失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除失敗: {str(e)}")
