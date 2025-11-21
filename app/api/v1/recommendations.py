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
from app.services.store_items import get_store_service
from app.services.weather import WeatherService

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
    
    # 解析簡單的 user-{uuid}-token 格式
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail="Token 格式錯誤")
    
    # 提取 UUID
    user_id = token[len(prefix):-len(suffix)]
    
    try:
        import uuid as _uuid
        _uuid.UUID(user_id)  # 驗證格式
    except Exception:
        raise HTTPException(status_code=401, detail="Token 格式錯誤")
    
    # 查詢使用者
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="使用者不存在")
    
    return user

def resolve_image_url(uri: str) -> str:
    """轉換圖片 URI 為可訪問的 URL"""
    if not uri:
        return ""
    if uri.startswith("gs://"):
        from app.services.storage import generate_signed_url_from_gcs_uri
        return generate_signed_url_from_gcs_uri(uri, expiration_minutes=60)
    return uri

def get_clothing_suggestions(item: WardrobeItem, all_items: List[WardrobeItem], seed: int = None) -> List[Dict[str, Any]]:
    """為指定衣物生成完整的穿搭建議
    
    搭配邏輯（組成完整一套）：
    - 上衣 -> 推薦下身（褲子/裙子）+ 配件/包包
    - 褲子 -> 推薦上衣 + 配件/包包
    - 裙子 -> 推薦上衣 + 配件/包包
    - 洋裝 -> 推薦外套 + 配件/包包
    - 外套 -> 推薦上衣 + 下身（褲子/裙子）
    - 配件/包包/鞋子 -> 推薦上衣 + 下身
    
    Args:
        item: 主要衣物
        all_items: 所有可用衣物
        seed: 隨機種子，用於固定每日推薦結果
    """
    
    # 如果提供了種子，設置隨機種子以確保結果可重現
    if seed is not None:
        random.seed(seed)
    
    def get_category(clothing_item):
        """獲取衣物類別"""
        cat = getattr(clothing_item, "category", None)
        if hasattr(cat, "value"):
            return cat.value
        return cat
    
    def format_item(clothing_item):
        """格式化衣物資訊"""
        db_uri = getattr(clothing_item, "cover_image_url", getattr(clothing_item, "cover_img_url", "")) or ""
        img_url = resolve_image_url(db_uri)
        return {
            "id": str(getattr(clothing_item, "id", "")),
            "name": getattr(clothing_item, "name", "") or "",
            "category": get_category(clothing_item),
            "imageUrl": img_url,
        }
    
    item_category = get_category(item)
    
    # 排除自己
    available_items = [i for i in all_items if i.id != item.id]
    
    # 按類別分組
    items_by_category = {}
    for clothing_item in available_items:
        cat = get_category(clothing_item)
        if cat not in items_by_category:
            items_by_category[cat] = []
        items_by_category[cat].append(clothing_item)
    
    suggestions = []
    
    # 根據主要衣物類別決定搭配策略
    if item_category == "上衣":
        # 上衣 -> 下身 + 配件/包包
        # 優先選擇下身
        bottoms = items_by_category.get("褲子", []) + items_by_category.get("裙子", [])
        if bottoms:
            # 排序以確保穩定性
            bottoms_sorted = sorted(bottoms, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(bottoms_sorted)))
        # 添加配件或包包
        accessories = items_by_category.get("配件", []) + items_by_category.get("包包", [])
        if accessories:
            accessories_sorted = sorted(accessories, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(accessories_sorted)))
        elif items_by_category.get("鞋子", []):
            shoes_sorted = sorted(items_by_category["鞋子"], key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(shoes_sorted)))
            
    elif item_category in ["褲子", "裙子"]:
        # 下身 -> 上衣 + 配件/包包
        tops = items_by_category.get("上衣", [])
        if tops:
            tops_sorted = sorted(tops, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(tops_sorted)))
        # 添加配件或包包
        accessories = items_by_category.get("配件", []) + items_by_category.get("包包", [])
        if accessories:
            accessories_sorted = sorted(accessories, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(accessories_sorted)))
        elif items_by_category.get("鞋子", []):
            shoes_sorted = sorted(items_by_category["鞋子"], key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(shoes_sorted)))
            
    elif item_category == "洋裝":
        # 洋裝 -> 外套 + 配件/包包
        outers = items_by_category.get("外套", [])
        if outers:
            outers_sorted = sorted(outers, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(outers_sorted)))
        accessories = items_by_category.get("配件", []) + items_by_category.get("包包", [])
        if accessories:
            accessories_sorted = sorted(accessories, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(accessories_sorted)))
            
    elif item_category == "外套":
        # 外套 -> 上衣 + 下身
        tops = items_by_category.get("上衣", [])
        if tops:
            tops_sorted = sorted(tops, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(tops_sorted)))
        bottoms = items_by_category.get("褲子", []) + items_by_category.get("裙子", [])
        if bottoms:
            bottoms_sorted = sorted(bottoms, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(bottoms_sorted)))
            
    elif item_category in ["配件", "包包", "鞋子"]:
        # 配件/包包/鞋子 -> 上衣 + 下身
        tops = items_by_category.get("上衣", [])
        if tops:
            tops_sorted = sorted(tops, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(tops_sorted)))
        bottoms = items_by_category.get("褲子", []) + items_by_category.get("裙子", [])
        if bottoms:
            bottoms_sorted = sorted(bottoms, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(bottoms_sorted)))
    
    else:
        # 其他類別：隨機推薦上衣和下身
        tops = items_by_category.get("上衣", [])
        if tops:
            tops_sorted = sorted(tops, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(tops_sorted)))
        bottoms = items_by_category.get("褲子", []) + items_by_category.get("裙子", [])
        if bottoms:
            bottoms_sorted = sorted(bottoms, key=lambda x: str(x.id))
            suggestions.append(format_item(random.choice(bottoms_sorted)))
    
    # 重置隨機種子
    if seed is not None:
        random.seed()
    
    return suggestions

@router.get("/daily")
def get_daily_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """取得今日推薦（基於超過90天未穿的衣物）"""
    try:
        from sqlalchemy import text
        import json
        
        # 查詢該使用者的今日推薦
        result = db.execute(text("""
            SELECT id, kind, payload, expires_at, created_at
            FROM recommendations
            WHERE user_id = :user_id
            AND kind = 'daily_inactive'
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
        """), {"user_id": str(current_user.id)})
        
        recommendations = []
        for row in result:
            payload = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)
            
            # 解析圖片 URL
            image_url = payload.get("imageUrl", "")
            if image_url:
                image_url = resolve_image_url(image_url)
            
            recommendations.append({
                "id": str(row.id),
                "item": {
                    "id": payload.get("item_id"),
                    "name": payload.get("name"),
                    "category": payload.get("category"),
                    "color": payload.get("color"),
                    "imageUrl": image_url,
                    "daysInactive": payload.get("daysInactive"),
                },
                "reason": payload.get("reason"),
                "suggestions": []  # 可以加入搭配建議
            })
        
        logger.info(f"[daily] 為使用者 {current_user.id} 找到 {len(recommendations)} 筆推薦")
        
        return recommendations
        
    except Exception as e:
        logger.exception("[daily] 取得今日推薦失敗")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/inactive")
async def get_inactive_recommendations(
    days: int = Query(30, ge=1, le=365, description="未穿天數門檻"),
    city: Optional[str] = Query(None, description="城市名稱（用於天氣查詢）"),
    lat: Optional[float] = Query(None, description="緯度（用於天氣查詢）"),
    lon: Optional[float] = Query(None, description="經度（用於天氣查詢）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        # 取得天氣資訊
        weather_service = WeatherService()
        weather_info = await weather_service.get_weather(city=city, lat=lat, lon=lon)
        logger.info(f"[inactive] 天氣資訊: {weather_info}")
        # 計算截止日期（使用當前時間減去指定天數）
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        logger.info("[inactive] days=%s, user_id=%s", days, current_user.id)

        # 查詢該使用者超過指定天數未穿的衣物
        # 使用 last_worn_at（優先）或 created_at
        inactive_items = (
            db.query(WardrobeItem)
            .filter(WardrobeItem.user_id == current_user.id)
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
                "item": item,  # 保存完整的item對象，稍後用於生成搭配建議
                "item_data": {
                    "id": str(item.id),
                    "name": item.name,
                    "imageUrl": image_url or "/placeholder.jpg",
                    "category": raw_category,
                    "color": item.color,
                    "last_worn": base_dt.isoformat() if base_dt else None,
                    "created_at": normalize_dt(getattr(item, "created_at", None)).isoformat() if getattr(item, "created_at", None) else None,
                    "daysInactive": days_inactive
                },
                "suggestions": [],
                "_days_inactive_for_sort": days_inactive or 0  # 用於排序的臨時字段
            })

            logger.info(
                "[inactive] item id=%s name=%s days=%s user_id=%s last_worn_at=%s created_at=%s",
                getattr(item, "id", None),
                getattr(item, "name", None),
                days_inactive,
                getattr(item, "user_id", None),
                getattr(item, "last_worn_at", None),
                getattr(item, "created_at", None),
            )
        
        # 按days_inactive排序（最接近30天的優先）並取前3件
        result.sort(key=lambda x: x["_days_inactive_for_sort"])
        result = result[:3]

        # 使用當前日期作為隨機種子，確保同一天內推薦結果和搭配固定
        today = datetime.now(timezone.utc).date()
        daily_seed = int(today.strftime("%Y%m%d")) + int(str(current_user.id)[:8], 16)
        random.seed(daily_seed)
        
        # 獲取用戶所有衣物用於生成搭配建議
        all_user_items = (
            db.query(WardrobeItem)
            .filter(WardrobeItem.user_id == current_user.id)
            .all()
        )
        
        # 為每件推薦的衣物生成搭配建議（使用相同的種子確保搭配也固定）
        # 同時混合店家商品
        final_result = []
        store_service = get_store_service()
        
        # 取得使用者性別（用於店家商品篩選）
        user_gender = "women"  # 預設女生，可從 current_user.gender 取得
        if hasattr(current_user, "gender"):
            user_gender = "women" if current_user.gender in ["female", "女", "女生"] else "men"
        
        for idx, entry in enumerate(result):
            item_obj = entry["item"]
            item_data = entry["item_data"]
            
            # 為每個item使用不同但固定的種子
            item_seed = daily_seed + idx
            
            # 生成衣櫃搭配建議
            wardrobe_suggestions = get_clothing_suggestions(item_obj, all_user_items, seed=item_seed)
            
            # 標記衣櫃商品來源
            for suggestion in wardrobe_suggestions:
                suggestion["source"] = "wardrobe"
                suggestion["purchaseUrl"] = None
            
            # 根據類別從店家取得搭配商品（1-2件）
            random.seed(item_seed + 100)  # 使用不同種子但每日固定
            store_items = []
            item_category = item_data.get("category", "")
            
            # 根據類別決定要推薦的店家商品類別
            if item_category == "上衣":
                # 推薦下身或配件
                store_items = store_service.get_items(gender=user_gender, category="褲子", limit=2)
                if not store_items:
                    store_items = store_service.get_items(gender=user_gender, category="包包", limit=2)
            elif item_category in ["褲子", "裙子"]:
                # 推薦上衣或配件
                store_items = store_service.get_items(gender=user_gender, category="上衣", limit=2)
            elif item_category == "外套":
                # 推薦上衣或下身
                store_items = store_service.get_items(gender=user_gender, category="上衣", limit=1)
            
            # 隨機選取 1 件店家商品混入搭配
            if store_items:
                selected_store = random.choice(store_items)
                wardrobe_suggestions.append(selected_store)
            
            # 標記主要推薦項目來源
            item_data["source"] = "wardrobe"
            item_data["purchaseUrl"] = None
            
            final_result.append({
                "item": item_data,
                "suggestions": wardrobe_suggestions,
                "weather": weather_info  # 附帶天氣資訊
            })
        
        # 額外加入純店家商品推薦（依色系）
        store_palettes = store_service.get_items_by_palette_all(gender=user_gender)
        
        # 重置隨機種子
        random.seed()
        
        logger.info(f"[inactive] 返回 {len(final_result)} 筆推薦（今日種子: {daily_seed}），包含搭配建議與店家商品")
        
        return {
            "recommendations": final_result,
            "storePalettes": store_palettes,  # 其他色系店家商品
            "weather": weather_info
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()  # 打印完整錯誤堆疊
        raise HTTPException(status_code=500, detail=str(e))
