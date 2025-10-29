"""
修正後的衣物路由 - 統一圖片 URL 處理
放置位置: app/api/v1/clothes.py
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
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


router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

security_optional = HTTPBearer(auto_error=False)

# 是否啟用 GCS（從環境變數讀取）
USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

# ========== 臨時 DEBUG 碼 START ==========
print(f"DEBUG: USE_GCS 實際值: {USE_GCS}")
print(f"DEBUG: GCS_BUCKET_NAME 實際值: {GCS_BUCKET_NAME}")
# ========== 臨時 DEBUG 碼 END ==========

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
        
        # 2. 儲存原始檔案
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
        
        # 3. 去背處理
        if remove_bg_enabled:
            logger.info(f"執行去背: {final_file_path}")
            proc_res = process_image(str(final_file_path))
            processed_file_path = Path(proc_res["processed_image_path"])
            final_file_path = processed_file_path
        
        # 4. AI 辨識
        if ai_detect_enabled:
            logger.info(f"執行 AI 辨識: {final_file_path}")
            analysis_result = analyze_clothing_type(str(final_file_path), ai_detect_enabled=True)
            
            if analysis_result.get("category") and analysis_result["category"] != "特殊":
                category = analysis_result["category"]
            if analysis_result.get("colors"):
                color = analysis_result["colors"][0]
            if analysis_result.get("style"):
                style = analysis_result["style"]
        
        # 5. 決定最終儲存位置
        try:
            cat_enum = CategoryEnum(category) if category in [e.value for e in CategoryEnum] else CategoryEnum.TOP
        except:
            cat_enum = CategoryEnum.TOP
        
        # ✅ 關鍵修改：統一的檔案儲存邏輯
        if USE_GCS and GCS_BUCKET_NAME:
            # 上傳到 GCS
            safe_cat = category.strip().replace("/", "_")
            gcs_path = f"clothes/{safe_cat}/{safe_stem}{final_file_path.suffix}"
            
            logger.info(f"上傳至 GCS: {gcs_path}")
            gcs_url = upload_file_to_gcs(
                str(final_file_path),
                GCS_BUCKET_NAME,
                gcs_path
            )
            cover_url = gcs_url  # 使用 GCS URL
            logger.info(f"GCS URL: {cover_url}")
        else:
            # 儲存到本地
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
        
        # 6. 建立資料庫記錄
        item = WardrobeItem(
            user_id=current_user.id,
            name=name or safe_stem,
            category=cat_enum,
            color=color or "",
            cover_image_url=cover_url,  # ✅ 直接儲存原始 URL
            tags=tags_list,
            attributes=attributes_dict,
            brand=attributes_dict.get("brand", ""),
            style=style if style else None,
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
        if user:
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
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("取得衣物詳情失敗")
        raise HTTPException(status_code=500, detail="讀取衣物失敗")


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """刪除衣物"""
    try:
        try:
            parsed_id = int(item_id)
        except:
            parsed_id = item_id
        
        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")
        
        if item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限刪除此衣物")
        
        # 刪除圖片檔案（僅本地檔案）
        img_path = item.cover_image_url
        if img_path and img_path.startswith("/uploads/"):
            abs_path = Path(img_path.lstrip("/"))
            try:
                if abs_path.exists():
                    abs_path.unlink()
                    logger.info(f"已刪除圖片: {abs_path}")
            except Exception as e:
                logger.warning(f"刪除圖片失敗: {e}")
        
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