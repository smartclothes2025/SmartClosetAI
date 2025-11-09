"""
修正後的衣物路由 - 統一圖片 URL 處理
放置位置: app/api/v1/clothes.py
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, status, Body, Request
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
from app.services.storage import upload_file_to_gcs  # GCS 上傳服務

# 確保載入環境變數
from dotenv import load_dotenv
load_dotenv()

# ✅ 匯入圖片 URL 處理函數
def resolve_image_url(uri: str) -> str:
    """轉換圖片 URI 為可訪問的 URL"""
    if not uri:
        return ""
    if uri.startswith("gs://"):
        from app.services.storage import generate_signed_url_from_gcs_uri
        try:
            return generate_signed_url_from_gcs_uri(uri, expiration_minutes=60)
        except Exception as e:
            logger.warning(f"無法產生 GCS 簽署 URL: {e}")
            return ""
    return uri


# ✅ Pydantic 模型：衣物更新請求
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
                "attributes": {"brand": "Uniqlo", "size": "M"}
            }
        }


router = APIRouter()
logger = logging.getLogger(__name__)

security_optional = HTTPBearer(auto_error=False)

# ❌ 強制啟用 GCS，不再支援本地儲存
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "smartclothes_wardrobe")

if not GCS_BUCKET_NAME:
    logger.error("⚠️ GCS_BUCKET_NAME 未設定，上傳功能將無法使用！")

logger.info(f"✅ GCS 模式已啟用，Bucket: {GCS_BUCKET_NAME}")

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
    "bottoms": "褲子",  # bottoms 也映射到褲子
    # 已經是中文的直接通過
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

def _sanitize_name(raw: str) -> str:
    """清理檔案名稱"""
    raw = (raw or "").strip()
    if not raw:
        return "file"
    return re.sub(r"[^\w\u4e00-\u9fff\-\s]", "_", raw)[:120].strip() or "file"


async def _get_optional_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[User]:
    """可選的使用者認證（允許訪客存取）"""
    if not credentials:
        return None
    
    token = credentials.credentials
    # 您的 token 解析邏輯
    prefix, suffix = "user-", "-token"
    
    if isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix):
        raw_id = token[len(prefix):-len(suffix)]
        try:
            parsed_id = int(raw_id)
        except:
            parsed_id = raw_id
        
        user = db.query(User).filter(User.id == parsed_id).first()
        return user
    return None


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
        # 1. 解析參數
        tags_list = json.loads(tags) if tags else []
        attributes_dict = json.loads(attributes) if attributes else {}
        
        ai_detect_enabled = ai_detect == "1"
        remove_bg_enabled = remove_bg == "1"
        
        # 轉換 category 從英文到中文
        category = CATEGORY_MAP.get(category.strip(), category.strip()) or "上衣"
        logger.info(f"收到 category: {category}")
        
        # 2. 儲存原始檔案到臨時位置(僅用於處理)
        safe_stem = _sanitize_name(name) if name.strip() else _sanitize_name(Path(file.filename).stem)
        orig_ext = Path(file.filename).suffix or ".jpg"
        
        # 使用系統臨時目錄
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "smartcloset_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_name = f"{safe_stem}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_temp{orig_ext}"
        temp_file_path = temp_dir / temp_file_name
        
        with open(temp_file_path, "wb") as out:
            file.file.seek(0)
            shutil.copyfileobj(file.file, out)
        
        final_file_path = temp_file_path
        
        # 3. 去背處理
        if remove_bg_enabled:
            logger.info(f"執行去背: {final_file_path}")
            proc_res = process_image(str(final_file_path))
            processed_file_path = Path(proc_res["processed_image_path"])
            final_file_path = processed_file_path
        
        # 4. AI 辨識
        if ai_detect_enabled:
            logger.info(f"執行 AI 辨識: {final_file_path}")
            analysis_result = analyze_clothing_type(str(final_file_path))
            
            if analysis_result.get("category") and analysis_result["category"] != "special":
                # AI 回傳的是英文類別，需要轉換成中文
                ai_category_en = analysis_result["category"]
                ai_category_map = {
                    "tops": "上衣",
                    "pants": "褲子",
                    "skirts": "裙子",
                    "dresses": "洋裝",
                    "outerwear": "外套",
                    "shoes": "鞋子",
                    "bags": "包包",
                    "hats": "帽子",
                    "socks": "襪子",
                    "jewelry": "配件",
                    "bottoms": "褲子",
                    "pantsuits": "洋裝"
                }
                category = ai_category_map.get(ai_category_en, category)
                logger.info(f"AI 辨識類別: {ai_category_en} -> {category}")
            
            if analysis_result.get("colors"):
                color = analysis_result["colors"][0]
            if analysis_result.get("style"):
                style = analysis_result["style"]
        
        # 5. 上傳到 GCS (強制,不再支援本地儲存)
        try:
            cat_enum = CategoryEnum(category) if category in [e.value for e in CategoryEnum] else CategoryEnum.TOP
        except:
            cat_enum = CategoryEnum.TOP
        
        print(f"\n{'='*60}")
        print(f"[上傳] 開始處理: {name or safe_stem}")
        print(f"[配置] GCS 模式 (強制), BUCKET={GCS_BUCKET_NAME}")
        print(f"{'='*60}")
        
        if not GCS_BUCKET_NAME:
            raise HTTPException(status_code=500, detail="GCS_BUCKET_NAME 未設定，無法上傳圖片")
        
        # 準備 GCS 路徑: wardrobe/{user_id}/{category}/{filename}
        user_id_str = str(current_user.id)
        
        # 類別映射到 GCS 路徑
        category_gcs_map = {
            "上衣": "tops",
            "裙子": "skirts", 
            "褲子": "bottoms",
            "洋裝": "dresses",
            "外套": "outerwear",
            "鞋子": "shoes",
            "帽子": "hats",
            "包包": "bags",
            "配件": "accessories",
        }
        category_gcs = category_gcs_map.get(category, "tops")
        
        gcs_path = f"wardrobe/{user_id_str}/{category_gcs}/{safe_stem}{final_file_path.suffix}"
        
        # 讀取檔案內容為 bytes
        with open(final_file_path, "rb") as f:
            file_bytes = f.read()
        
        # 決定 MIME type
        ext = final_file_path.suffix.lower()
        if ext == ".png":
            mime_type = "image/png"
        elif ext in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif ext == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"
        
        print(f"[GCS] 上傳至: gs://{GCS_BUCKET_NAME}/{gcs_path}")
        logger.info(f"上傳至 GCS: gs://{GCS_BUCKET_NAME}/{gcs_path}")
        
        try:
            cover_url = upload_file_to_gcs(
                file_bytes=file_bytes,
                destination_blob_name=gcs_path,
                mime_type=mime_type,
                bucket_name=GCS_BUCKET_NAME,
                public=False,
            )
            print(f"[成功] GCS 上傳成功: {cover_url}")
            logger.info(f"✅ GCS 上傳成功: {cover_url}")
        except Exception as gcs_error:
            print(f"[錯誤] GCS 上傳失敗: {gcs_error}")
            logger.error(f"❌ GCS 上傳失敗: {gcs_error}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"圖片上傳失敗: {str(gcs_error)}")
        
        # 6. 建立資料庫記錄（style 不受限制，可以是任何文字）
        item = WardrobeItem(
            user_id=current_user.id,
            name=name or safe_stem,
            category=cat_enum,
            color=color or "",
            cover_image_url=cover_url,  # ✅ 直接儲存原始 URL
            tags=tags_list,
            attributes=attributes_dict,
            brand=attributes_dict.get("brand", ""),
            style=style if style else None,  # 直接使用 style，不驗證
        )
        
        db.add(item)
        db.commit()
        db.refresh(item)
        
        # ✅ 回傳時使用統一的 URL 處理
        resolved_url = resolve_image_url(item.cover_image_url)
        
        return {
            "message": "上傳成功",
            "item": {
                "id": str(item.id),
                "name": item.name,
                "category": item.category.value,
                "color": item.color,
                "img": resolved_url,  # ✅ 統一處理後的 URL
                "daysInactive": None,
                "owner_display_name": item.user.display_name if item.user else "",
                "last_worn_at": item.last_worn_at.isoformat() if item.last_worn_at else None,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("上傳失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"上傳失敗: {str(e)}")
    finally:
        # 清理臨時檔案
        for path in [temp_file_path, processed_file_path]:
            if path and path.exists():
                try:
                    os.unlink(path)
                    logger.debug(f"已刪除臨時檔案: {path}")
                except Exception as e:
                    logger.warning(f"無法刪除臨時檔案 {path}: {e}")


@router.get("/")
def list_clothes(
    limit: int = 50,
    scope: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(_get_optional_current_user)
):
    """取得衣櫃清單"""
    try:
        # 訪客檢查
        if user:
            if user.id == 99 or user.email == "guest@local":
                return []
        
        q = db.query(WardrobeItem)
        # ✅ 判斷是否為管理者且請求所有衣物
        is_admin = user and getattr(user, 'role', None) == 'admin'
        if scope == "all" and is_admin:
            # 管理者請求所有衣物,不過濾 user_id
            logger.info(f"管理者 {user.id} 請求所有衣物")
        elif user:
            # 普通使用者只能看到自己的衣物
            q = q.filter(WardrobeItem.user_id == user.id)
        
        q = q.order_by(WardrobeItem.created_at.desc()).limit(limit)
        rows = q.all()
        
        result = []
        now = datetime.now(timezone.utc)
        
        for item in rows:
            # ✅ 使用統一的 URL 處理工具
            img_url = resolve_image_url(item.cover_image_url)
            
            # 追蹤 URL 轉換
            logger.info(f"Item ID {item.id}: DB-URI='{item.cover_image_url}', Resolved-URL='{img_url}'")

            # 計算 daysInactive
            dt = item.updated_at or item.created_at
            days = None
            if dt:
                delta = now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
                days = delta.days
            
            result.append({
                "id": str(item.id),
                "name": item.name or "",
                "category": item.category.value if item.category else "",
                "color": item.color or "",
                "img": img_url,  # ✅ 統一處理後的 URL
                "daysInactive": days,
                "owner_display_name": item.user.display_name if item.user else "",
                "user_id": item.user_id,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            })
        
        return result
        
    except Exception as e:
        logger.exception("取得衣櫃清單失敗")
        raise HTTPException(status_code=500, detail="讀取衣櫃失敗")


@router.get("/{item_id}")
def get_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
):
    """取得單一衣物詳情"""
    try:
        try:
            parsed_id = int(item_id)
        except:
            parsed_id = item_id
        
        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")
        
        # ✅ 使用統一的 URL 處理
        img_url = resolve_image_url(item.cover_image_url)
        
        dt = item.updated_at or item.created_at
        days = None
        now = datetime.now(timezone.utc)
        if dt:
            delta = now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
            days = delta.days
        
        return {
            "id": str(item.id),
            "name": item.name or "",
            "category": item.category.value if item.category else "",
            "color": item.color or "",
            "img": img_url,  # ✅ 統一處理後的 URL
            "daysInactive": days,
            "owner_display_name": item.user.display_name if item.user else "",
            "tags": item.tags or [],
            "attributes": item.attributes or {},
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("取得衣物詳情失敗")
        raise HTTPException(status_code=500, detail="讀取衣物失敗")


@router.patch("/{item_id}")
@router.put("/{item_id}")
async def update_clothes_item(
    item_id: str,
    request: Request,
    body: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新衣物資訊（支援部分更新,同時支援 PATCH 和 PUT 方法,接受 JSON 格式）"""
    try:
        logger.info(f"收到更新請求 - item_id: {item_id}")
        logger.info(f"原始 request body: {body}")

        # 支援兩種前端格式：{ "payload": {...} } 或 直接傳 {"name":..., "color":...}
        data = None
        if isinstance(body, dict):
            data = body.get('payload', body)

        # 如果 FastAPI 沒有解析到 body（body is None），嘗試直接從 request 讀取原始 JSON（更健壯）
        if data is None:
            try:
                raw = await request.json()
                if isinstance(raw, dict):
                    data = raw.get('payload', raw)
            except Exception as e:
                logger.debug(f"無法從 request.json() 取得 body: {e}")

        # 若仍無 data，返回更清楚的錯誤（讓前端更容易除錯）
        if data is None:
            raise HTTPException(status_code=422, detail="缺少 request body 或 payload")

        # 使用 Pydantic 驗證（pydantic v2）
        try:
            payload = ClothesUpdateRequest.model_validate(data)
        except Exception as e:
            logger.warning(f"無法解析更新資料: {e}")
            raise HTTPException(status_code=422, detail=f"資料驗證失敗: {str(e)}")

        logger.info(f"更新資料 (validated): {payload.model_dump(exclude_none=True)}")

        # 從 payload 提取值
        name = payload.name
        category = payload.category
        color = payload.color
        tags = payload.tags
        attributes = payload.attributes
        style = payload.style
        brand = payload.brand
        
        # 解析 item_id
        try:
            parsed_id = int(item_id)
        except:
            parsed_id = item_id
        
        # 查詢衣物
        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")
        
        # 檢查權限：管理員可以編輯所有衣物，一般使用者只能編輯自己的
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if not is_admin and item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限編輯此衣物")
        
        # 記錄管理員操作
        if is_admin and item.user_id != current_user.id:
            logger.info(f"管理員 {current_user.id} 編輯了使用者 {item.user_id} 的衣物 {item_id}")
        
        # 更新欄位（僅更新有提供的欄位）
        if name is not None:
            item.name = name
            logger.info(f"更新 name: {name}")
        
        if category is not None:
            # 轉換 category 從英文到中文
            category_mapped = CATEGORY_MAP.get(category.strip(), category.strip())
            try:
                cat_enum = CategoryEnum(category_mapped) if category_mapped in [e.value for e in CategoryEnum] else None
                if cat_enum:
                    item.category = cat_enum
                    logger.info(f"更新 category: {cat_enum.value}")
            except Exception as e:
                logger.warning(f"無效的 category: {category}, 錯誤: {e}")
        
        if color is not None:
            item.color = color
            logger.info(f"更新 color: {color}")
        
        if style is not None:
            # 嘗試從資料庫取得 style_enum 的允許值，避免直接寫入不合法的 enum 導致 500
            try:
                enum_name = 'style_enum'
                rows = db.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = :name"), {"name": enum_name}).fetchall()
                allowed_values = [r[0] for r in rows]
            except Exception as _e:
                allowed_values = None
                logger.debug(f"無法查詢 enum 值: {_e}")

            if allowed_values:
                if style in allowed_values:
                    item.style = style
                    logger.info(f"更新 style: {style}")
                else:
                    logger.warning(f"收到未知的 style 值，跳過更新 style: {style}; 允許值: {allowed_values}")
            else:
                # 無法查詢 enum，採取保守策略：嘗試直接設定（若失敗會在 commit 時捕捉）
                item.style = style
                logger.info(f"嘗試更新 style（未驗證 enum）: {style}")
        
        if brand is not None:
            item.brand = brand
            logger.info(f"更新 brand: {brand}")
        
        if tags is not None:
            item.tags = tags
            logger.info(f"更新 tags: {tags}")
        
        if attributes is not None:
            item.attributes = attributes
            logger.info(f"更新 attributes: {attributes}")
        
        # 更新時間戳記
        item.updated_at = datetime.now(timezone.utc)
        
        # ✅ 記錄更新前的值
        logger.info(f"準備提交更新 - item_id: {item.id}, name: {item.name}, color: {item.color}, updated_at: {item.updated_at}")
        
        try:
            db.commit()
            logger.info(f"✓ db.commit() 執行成功")
        except Exception as commit_error:
            logger.error(f"✗ db.commit() 失敗: {commit_error}")
            db.rollback()
            raise
        
        try:
            db.refresh(item)
            logger.info(f"✓ db.refresh() 執行成功")
        except Exception as refresh_error:
            logger.error(f"✗ db.refresh() 失敗: {refresh_error}")
        
        # ✅ 記錄更新後的值
        logger.info(f"更新後的值 - item_id: {item.id}, name: {item.name}, color: {item.color}, updated_at: {item.updated_at}")
        
        logger.info(f"衣物 {item_id} 更新成功")
        
        # 回傳更新後的資料
        img_url = resolve_image_url(item.cover_image_url)
        
        dt = item.updated_at or item.created_at
        days = None
        now = datetime.now(timezone.utc)
        if dt:
            delta = now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
            days = delta.days
        
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
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新衣物失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失敗: {str(e)}")


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """刪除衣物（管理員可刪除所有使用者的衣物）"""
    try:
        try:
            parsed_id = int(item_id)
        except:
            parsed_id = item_id
        
        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")
        
        # 檢查權限：管理員可以刪除所有衣物，一般使用者只能刪除自己的
        is_admin = getattr(current_user, 'role', None) == 'admin'
        
        if not is_admin and item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限刪除此衣物")
        
        # 管理員刪除時記錄日誌
        if is_admin and item.user_id != current_user.id:
            logger.info(f"管理員 {current_user.id} 刪除了使用者 {item.user_id} 的衣物 {item_id}")
        
        # 刪除 GCS 圖片檔案
        img_uri = item.cover_image_url
        if img_uri:
            if img_uri.startswith("gs://"):
                # 刪除 GCS 檔案
                try:
                    from app.services.storage import delete_file_from_gcs
                    success = delete_file_from_gcs(img_uri)
                    if success:
                        logger.info(f"✅ 已刪除 GCS 圖片: {img_uri}")
                    else:
                        logger.warning(f"⚠️ GCS 圖片刪除失敗或不存在: {img_uri}")
                except Exception as e:
                    logger.warning(f"⚠️ 刪除 GCS 圖片時發生錯誤: {e}")
            elif img_uri.startswith("/uploads/"):
                # 舊資料的本地檔案 (向下相容)
                abs_path = Path(img_uri.lstrip("/"))
                try:
                    if abs_path.exists():
                        abs_path.unlink()
                        logger.info(f"✅ 已刪除本地圖片: {abs_path}")
                except Exception as e:
                    logger.warning(f"⚠️ 刪除本地圖片失敗: {e}")
        
        db.delete(item)
        db.commit()
        
        # ✅ 204 狀態碼不應回傳內容
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("刪除衣物失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除失敗: {str(e)}")