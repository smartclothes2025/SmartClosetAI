from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_, and_
import logging
import random

from app.core.db import get_db
from app.models.wardrobe import WardrobeItem, Wardrobe
from app.models.auth import User
from app.api.v1.auth import get_current_user

logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

security_strict = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/recommendations", tags=["推薦"])

def current_user_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_strict),
    db: Session = Depends(get_db),
) -> User:
    """從 Authorization Bearer 取得當前用戶"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供 Authorization Bearer")
    token = credentials.credentials
    try:
        return get_current_user(token=token, db=db)
    except TypeError:
        return get_current_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="登入已過期或無效")

def resolve_image_url(uri: str) -> str:
    """轉換圖片 URI 為可訪問的 URL"""
    if not uri:
        return ""
    if uri.startswith("gs://"):
        from app.services.storage import generate_signed_url_from_gcs_uri
        return generate_signed_url_from_gcs_uri(uri, expiration_minutes=60)
    return uri

def get_clothing_suggestions(item: WardrobeItem, all_items: List[WardrobeItem], max_suggestions: int = 3) -> List[Dict[str, Any]]:
    """為指定衣物生成搭配建議
    
    簡單的搭配邏輯：
    - 上衣 -> 推薦褲子/裙子
    - 褲子/裙子 -> 推薦上衣/外套
    - 外套 -> 推薦上衣/褲子
    - 其他 -> 隨機推薦
    """
    
    category_map = {
        "上衣": ["褲子", "裙子"],
        "褲子": ["上衣", "外套"],
        "裙子": ["上衣", "外套"],
        "洋裝": ["外套", "包包", "鞋子"],
        "外套": ["上衣", "褲子", "裙子"],
    }
    
    item_category = getattr(item, "category", None)
    if hasattr(item_category, "value"):
        item_category = item_category.value
    
    # 獲取推薦類別
    preferred_categories = category_map.get(item_category, [])
    
    # 篩選候選項目（排除自己）
    candidates = [i for i in all_items if i.id != item.id]
    
    # 優先選擇推薦類別的衣物
    if preferred_categories:
        preferred = []
        others = []
        for candidate in candidates:
            cat = getattr(candidate, "category", None)
            if hasattr(cat, "value"):
                cat = cat.value
            if cat in preferred_categories:
                preferred.append(candidate)
            else:
                others.append(candidate)
        
        # 先從推薦類別選，不足再從其他補
        candidates = preferred + others
    
    # 隨機選取最多 max_suggestions 個
    selected = random.sample(candidates, min(len(candidates), max_suggestions))
    
    suggestions = []
    for s in selected:
        db_uri = getattr(s, "cover_image_url", getattr(s, "cover_img_url", "")) or ""
        img_url = resolve_image_url(db_uri)
        
        suggestions.append({
            "id": str(getattr(s, "id", "")),
            "name": getattr(s, "name", "") or "",
            "imageUrl": img_url,
        })
    
    return suggestions

@router.get("/inactive")
def get_inactive_recommendations(
    days: int = Query(90, ge=1, le=365, description="未穿天數門檻"),
    db: Session = Depends(get_db),
    # current_user: User = Depends(current_user_from_header),  # 暫時註解掉
):
    try:
        # 計算截止日期（使用當前時間減去指定天數）
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        logger.info("[inactive] days=%s", days)

        # 查詢超過指定天數未穿的衣物
        inactive_items = (
            db.query(WardrobeItem)
            .filter(
                or_(
                    and_(
                        WardrobeItem.last_worn_at.isnot(None),
                        WardrobeItem.last_worn_at < cutoff_date,
                    ),
                    and_(
                        WardrobeItem.last_worn_at.is_(None),
                        WardrobeItem.created_at < cutoff_date,
                    ),
                )
            )
            .all()
        )

        logger.info("[inactive] total candidates=%s", len(inactive_items))
        
        # 格式化返回數據
        def normalize_dt(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value
            if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
                return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
            return None

        now = datetime.now(timezone.utc)

        result = []
        for item in inactive_items:
            base_dt = normalize_dt(getattr(item, "last_worn_at", None)) or normalize_dt(getattr(item, "created_at", None))
            days_inactive = (now - base_dt).days if base_dt else None

            raw_category = getattr(item, "category", None)
            if hasattr(raw_category, "value"):
                raw_category = raw_category.value

            raw_image = getattr(item, "cover_image_url", None)
            image_url = resolve_image_url(raw_image) if raw_image else ""

            result.append({
                "item": {
                    "id": str(item.id),
                    "name": item.name,
                    "imageUrl": image_url or "/placeholder.jpg",
                    "category": raw_category,
                    "color": item.color,
                    "last_worn": base_dt.isoformat() if base_dt else None,
                    "created_at": normalize_dt(getattr(item, "created_at", None)).isoformat() if getattr(item, "created_at", None) else None,
                    "daysInactive": days_inactive
                },
                "suggestions": []  # 這裡可以添加搭配建議
            })

            logger.info(
                "[inactive] item id=%s name=%s days=%s user_id=%s last_worn=%s created_at=%s",
                getattr(item, "id", None),
                getattr(item, "name", None),
                days_inactive,
                getattr(item, "user_id", None),
                getattr(item, "last_worn_at", None),
                getattr(item, "created_at", None),
            )
        
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()  # 打印完整錯誤堆疊
        raise HTTPException(status_code=500, detail=str(e))
