from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
import shutil
import re
import logging
import json
from urllib.parse import quote

from app.core.db import get_db
from app.models.wardrobe import WardrobeItem, CategoryEnum
from app.models.auth import User
from app.api.v1.auth import get_current_user # 假設這裡也有 get_optional_current_user

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

UPLOAD_ROOT = Path("uploads")
try:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    logger.exception("無法建立 UPLOAD_ROOT")

STATIC_MOUNT_NAME = "uploads"
security_optional = HTTPBearer(auto_error=False)

def _sanitize_name(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "file"
    return re.sub(r"[^\w\u4e00-\u9fff\-\s]", "_", raw)[:120].strip() or "file"

# --- 模擬 'get_optional_current_user' (您應在 app.api.v1.auth 中實作) ---
# 由於我無法訪問 app.api.v1.auth，我在這裡提供一個模擬的依賴項
# 【重要：您應該使用您 app.api.v1.auth 中的實際函式】
async def _get_optional_current_user(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> Optional[User]:
    """取代原 list_clothes 中的手動解析 token 邏輯，並回傳 User 或 None"""
    if not credentials:
        return None
    
    token = credentials.credentials
    prefix = "user-"
    suffix = "-token"
    
    # 這裡複製您原先 list_clothes 中的 token 解析邏輯
    if isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix):
        raw_id = token[len(prefix):-len(suffix)]
        try:
            # 假設 User.id 是 Integer
            parsed_id = int(raw_id)
        except Exception:
            # 如果不是 Integer，則使用原始字串 (例如 UUID)
            parsed_id = raw_id
            
        user = db.query(User).filter(User.id == parsed_id).first()
        return user
    return None
# --------------------------------------------------------------------------

@router.post("/wardrobe", status_code=status.HTTP_201_CREATED)
async def upload_clothes(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form("上衣"),
    color: str = Form(""),
    tags: str = Form("[]"),
    attributes: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    
    try:
        try:
            tags_list = json.loads(tags) if tags else []
            if not isinstance(tags_list, list):
                tags_list = []
        except Exception:
            tags_list = []
        try:
            attributes_dict = json.loads(attributes) if attributes else {}
            if not isinstance(attributes_dict, dict):
                attributes_dict = {}
        except Exception:
            attributes_dict = {}

        # 轉換 category 為 CategoryEnum
        cat_enum = None
        try:
            # 確保 category 是有效的 CategoryEnum
            if category in [e.value for e in CategoryEnum]:
                cat_enum = CategoryEnum(category)
            else:
                # 預設為上衣
                cat_enum = CategoryEnum.TOP
        except Exception:
            cat_enum = CategoryEnum.TOP

        safe_cat = category.strip().replace("/", "_")
        dest_dir = UPLOAD_ROOT / safe_cat
        dest_dir.mkdir(parents=True, exist_ok=True)

        orig_ext = Path(file.filename).suffix or ""
        safe_stem = _sanitize_name(name) if name.strip() else _sanitize_name(Path(file.filename).stem)
        candidate = f"{safe_stem}{orig_ext}"
        save_path = dest_dir / candidate
        if save_path.exists():
            stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            candidate = f"{safe_stem}_{stamp}{orig_ext}"
            save_path = dest_dir / candidate

        try:
            with open(save_path, "wb") as out:
                file.file.seek(0)
                shutil.copyfileobj(file.file, out)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        cover_url = f"/{STATIC_MOUNT_NAME}/{safe_cat}/{candidate}"

        # 建立 WardrobeItem，確保 user_id 使用正確的 UUID 類型
        item_kwargs: Dict[str, Any] = {
            "user_id": current_user.id,  # current_user.id 應該是 UUID 類型
            "name": (name or safe_stem),
            "category": cat_enum,  # 使用 CategoryEnum
            "color": color or "",
            "cover_image_url": cover_url,
            "tags": tags_list,
            "attributes": attributes_dict,
        }

        # 從 attributes 中提取 brand 和 style
        if attributes_dict.get("brand"):
            item_kwargs["brand"] = attributes_dict.get("brand")
        if attributes_dict.get("style"):
            item_kwargs["style"] = attributes_dict.get("style")

        item = WardrobeItem(**item_kwargs)
        db.add(item)
        db.commit()
        db.refresh(item)

        resp = {
            "id": str(item.id),
            "name": item.name or "",
            "category": item.category.value if item.category else "",
            "color": item.color or "",
            "img": item.cover_image_url or cover_url,
            "daysInactive": None,
            "owner_display_name": item.user.display_name if item.user else "",
        }
        return {"message": "上傳成功", "item": resp}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_clothes failed")
        raise HTTPException(status_code=500, detail=f"上傳失敗: {e}")

@router.get("/")
def list_clothes(
    limit: int = 50,
    db: Session = Depends(get_db),
    # 【重大修訂：使用新的可選依賴項，取代手動解析 credentials】
    user: Optional[User] = Depends(_get_optional_current_user) 
):
    
    try:
        # 移除原先手動解析 token 的所有邏輯，直接使用注入的 user
        # user = None
        # if credentials and credentials.credentials:
        #    ... (已移除)

        q = db.query(WardrobeItem)
        if user:
            # 僅在使用者登入時，過濾出該使用者的衣物
            q = q.filter(WardrobeItem.user_id == user.id)
            
        q = q.order_by(WardrobeItem.created_at.desc()).limit(limit)
        rows = q.all()

        res: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for it in rows:
            # 處理 category - 使用 CategoryEnum
            cat = it.category.value if it.category else ""

            img = it.cover_image_url or ""
            # Normalize: 若沒有 leading /，補上；若是非 uploads 路徑仍保留
            if img and not img.startswith("/"):
                img = f"/{img.lstrip('/')}"
            # 若 img 不是以 /uploads 開頭而是以 /wardrobe，轉成 /uploads（兼容舊資料）
            if img and img.startswith("/wardrobe"):
                img = img.replace("/wardrobe", f"/{STATIC_MOUNT_NAME}", 1)

            # 計算 daysInactive
            dt = it.updated_at or it.created_at
            days = None
            try:
                if dt:
                    if dt.tzinfo is None:
                        delta = now - dt
                    else:
                        delta = now - dt.astimezone(timezone.utc)
                    days = delta.days
            except Exception:
                days = None

            res.append({
                "id": str(it.id),
                "name": it.name or "",
                "category": cat,
                "color": it.color or "",
                "img": img,
                "daysInactive": days,
                "owner_display_name": it.user.display_name if it.user else "",
            })

        return res
    except Exception as e:
        logger.exception("list_clothes failed")
        raise HTTPException(status_code=500, detail="讀取衣櫃失敗")

@router.get("/{item_id}")
def get_clothes_item(
    item_id: str,
    db: Session = Depends(get_db),
    # 這裡保留舊的 credentials 參數以維持 API 簽名，但實際上沒有使用它
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional) 
):
    try:
        # 嘗試將 item_id 轉換為整數
        try:
            parsed_id = int(item_id)
        except (ValueError, TypeError):
            # 如果無法轉換為整數，直接使用字符串
            parsed_id = item_id
        
        it = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not it:
            raise HTTPException(status_code=404, detail="找不到該衣物")

        # 處理 category - 使用 CategoryEnum
        cat = it.category.value if it.category else ""

        img = it.cover_image_url or ""
        if img and not img.startswith("/"):
            img = f"/{img.lstrip('/')}"
        if img.startswith("/wardrobe"):
            img = img.replace("/wardrobe", f"/{STATIC_MOUNT_NAME}", 1)

        dt = it.updated_at or it.created_at
        days = None
        now = datetime.now(timezone.utc)
        try:
            if dt:
                if dt.tzinfo is None:
                    delta = now - dt
                else:
                    delta = now - dt.astimezone(timezone.utc)
                days = delta.days
        except Exception:
            days = None

        return {
            "id": str(it.id),
            "name": it.name or "",
            "category": cat,
            "color": it.color or "",
            "img": img,
            "daysInactive": days,
            "owner_display_name": it.user.display_name if it.user else "",
            "tags": it.tags or [],
            "attributes": it.attributes if it.attributes is not None else {},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_clothes_item failed")
        raise HTTPException(status_code=500, detail="讀取衣物失敗")

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clothes_item(
    
    request: Request,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    刪除指定 ID 的衣服資料（限擁有者）
    """
    try:
        # 嘗試將 item_id 轉換為整數
        try:
            parsed_id = int(item_id)
        except (ValueError, TypeError):
            # 如果無法轉換為整數，直接使用字符串
            parsed_id = item_id
        
        # 找出衣服
        item = db.query(WardrobeItem).filter(WardrobeItem.id == parsed_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="找不到該衣物")

        # 確認使用者身份 - user_id 是 UUID 類型
        if item.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="沒有權限刪除此衣物")

        # 嘗試刪除圖片檔案（若存在）
        img_path = item.cover_image_url
        if img_path and img_path.startswith("/uploads/"):
            abs_path = Path(img_path.lstrip("/"))
            try:
                if abs_path.exists():
                    abs_path.unlink()
            except Exception:
                logger.warning(f"刪除圖片檔失敗: {abs_path}")

        # 刪除資料庫記錄
        db.delete(item)
        db.commit()

        return {"message": "刪除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_clothes_item failed")
        raise HTTPException(status_code=500, detail=f"刪除衣物失敗: {e}")