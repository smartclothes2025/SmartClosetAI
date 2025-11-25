from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_, and_, text
import logging
import random

from app.core.db import get_db
from app.models.wardrobe import WardrobeItem, Wardrobe
from app.models.auth import User
from app.models.recommendation import Recommendation
from app.models.daily_color_outfit import DailyColorOutfit
from app.api.v1.auth import get_current_user
from app.services.store_items import get_store_service
from app.services.weather import WeatherService
from app.services.outfit_planner_ai import (
    outfit_planner_ai_service,
    build_outfit_payload,
    map_color_to_family,
    map_category,
    normalise_styles,
    OutfitPlannerPayload,
)

logger = logging.getLogger("uvicorn.error")
logging.basicConfig(level=logging.INFO)

security_strict = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/recommendations", tags=["推薦"])

 

COLOR_FAMILY3_PRIORITY = ["neutral", "earth", "cool"]

COLOR_FAMILY3_CONFIG: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "name": "中性色系",
        "palette": ["#F5F5F5", "#D3D3D3", "#808080", "#2F4F4F"],
    },
    "earth": {
        "name": "大地暖色系",
        "palette": ["#F5DEB3", "#D2B48C", "#C19A6B", "#8B4513"],
    },
    "cool": {
        "name": "清爽冷色系",
        "palette": ["#87CEEB", "#4169E1", "#32CD32", "#006400"],
    },
}

# 舊五色系（中文）對應到三色系
FIVE_TO_THREE_FAMILY_MAP = {
    "中性": "neutral",
    "卡其棕": "earth",
    "藍": "cool",
    "紅粉": "earth",
    "綠": "cool",
}


def normalise_gender_from_user(user: User, db: Optional[Session] = None) -> str:
    """將使用者的 gender/sex 正規化為 "men" 或 "women"。

    優先順序：
    1. User.gender 屬性（若有）
    2. body_metrics.sex 最新一筆（需提供 db）
    3. 預設 women
    """
    raw: Optional[str] = None

    # 1) 直接從 User 模型讀 gender 欄位（若有）
    if hasattr(user, "gender") and getattr(user, "gender", None):
        raw = getattr(user, "gender")

    # 2) 從 body_metrics.sex 讀取（若有 db 傳入且尚未取得）
    if raw is None and db is not None:
        try:
            row = db.execute(
                text(
                    "SELECT sex FROM body_metrics "
                    "WHERE user_id = :uid "
                    "ORDER BY recorded_at DESC "
                    "LIMIT 1"
                ),
                {"uid": getattr(user, "id", None)},
            ).mappings().first()
            if row:
                raw = row.get("sex")
        except Exception:
            # 失敗時不影響主流程，後續使用預設邏輯
            pass

    if not raw:
        return "women"

    v = str(raw).strip().lower()

    # 先判斷女性，避免 "women" 被誤判為 men
    if any(token in v for token in ["女", "female", "woman", "women", "girl"]):
        return "women"
    if any(token in v for token in ["男", "male", "man", "men", "boy"]):
        return "men"

    # 直接使用 men / women 的情況
    if v in ["men", "man"]:
        return "men"
    if v in ["women", "woman"]:
        return "women"

    return "women"


def map_color_to_3_family(color: Optional[str]) -> str:
    """將顏色字串映射到三色系之一。

    優先：透過既有的 map_color_to_family 取得五色系中文名稱，再映射到三色系。
    其次：根據英文 / 中文關鍵字粗略判斷。
    """
    if not color:
        return "neutral"

    # 優先使用既有五色系映射
    try:
        family5 = map_color_to_family(color)
        fam3 = FIVE_TO_THREE_FAMILY_MAP.get(family5)
        if fam3:
            return fam3
    except Exception:
        pass

    c = str(color).lower()

    # neutral: 黑白灰、深藍、牛仔
    if any(k in c for k in ["white", "black", "gray", "grey", "navy", "denim"]):
        return "neutral"
    if any(k in color for k in ["白", "黑", "灰", "牛仔"]):
        return "neutral"

    # earth: 卡其、咖啡、米色、膚色、駝、粉紅、紅
    if any(k in c for k in ["beige", "khaki", "brown", "camel", "ivory", "tan", "sand", "oat", "cream", "pink", "red"]):
        return "earth"
    if any(k in color for k in ["卡其", "咖啡", "米", "膚", "棕", "駝", "粉", "紅"]):
        return "earth"

    # cool: 藍、綠、藍綠
    if any(k in c for k in ["blue", "green", "teal", "olive", "turquoise", "aqua", "cyan"]):
        return "cool"
    if any(k in color for k in ["藍", "綠"]):
        return "cool"

    return "neutral"

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

        # 🤖 AI 搭配服務整合
        ai_recommendations = await _generate_ai_recommendations(
            current_user=current_user,
            inactive_items=inactive_items[:3],  # 只用前3個最需要推薦的項目
            weather_info=weather_info,
            db=db
        )
        
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
        user_gender = normalise_gender_from_user(current_user, db=db)

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


async def _generate_ai_recommendations(
    current_user: User,
    inactive_items: List[WardrobeItem],
    weather_info: Optional[Dict[str, Any]],
    db: Session
) -> Optional[Dict[str, Any]]:
    """
    使用 AI 搭配服務生成推薦並寫入 recommendations 表
    """
    try:
        logger.info(f"[AI] 開始為用戶 {current_user.id} 生成 AI 搭配推薦")
        
        if not inactive_items:
            logger.warning("[AI] 沒有未穿衣物，跳過 AI 推薦")
            return None
            
        # 準備衣櫃資料
        wardrobe_data = []
        for item in inactive_items:
            raw_category = getattr(item, "category", None)
            category_str = raw_category.value if hasattr(raw_category, "value") else str(raw_category)
            
            # 計算未穿天數
            now = datetime.now(timezone.utc)
            last_worn = getattr(item, "last_worn_at", None) or getattr(item, "created_at", None)
            days_inactive = (now - last_worn).days if last_worn else 999
            
            wardrobe_data.append({
                "id": str(item.id),
                "name": item.name or f"{category_str}_{item.id}",
                "category": map_category(category_str),
                "color": item.color or "未知",
                "color_family5": map_color_to_family(item.color),
                "styles": normalise_styles(item.style),
                "source": "wardrobe",
                "last_worn_days": days_inactive,
                "image_url": getattr(item, "cover_image_url", "")
            })
        
        # 準備 Style Shop 資料
        store_service = get_store_service()
        user_gender = normalise_gender_from_user(current_user, db=db)

        store_data = []
        store_items = store_service.get_items(gender=user_gender, limit=10)
        for store_item in store_items:
            store_data.append({
                "id": str(store_item.get("id", "")),
                "name": store_item.get("name", ""),
                "category": map_category(store_item.get("category", "")),
                "color": store_item.get("color", ""),
                "color_family5": map_color_to_family(store_item.get("color", "")),
                "styles": normalise_styles(store_item.get("style", "")),
                "source": "store",
                "price": store_item.get("price"),
                "purchaseUrl": store_item.get("purchaseUrl")
            })
        
        # 決定今日主色調
        today_color = "中性"  # 預設
        if weather_info:
            temp = weather_info.get("temperature", 20)
            if temp < 15:
                today_color = "卡其棕"  # 冷天偏暖色
            elif temp > 25:
                today_color = "藍"      # 熱天偏涼色
        
        # 建構 AI 請求負載
        payload = build_outfit_payload(
            wardrobe_items=wardrobe_data,
            store_items=store_data,
            user_request="請根據久未穿著的衣物推薦今日搭配",
            today_main_color=today_color,
            gender=user_gender,
            weather=weather_info
        )
        
        # 呼叫 AI 服務
        def fallback_builder():
            return outfit_planner_ai_service.build_rule_based_plan(payload)
        
        ai_result, source, raw_text = outfit_planner_ai_service.generate_plan(
            payload, fallback_builder=fallback_builder
        )
        
        logger.info(f"[AI] 搭配生成完成，來源: {source}")
        
        # 將結果寫入 recommendations 表
        if ai_result:
            await _save_daily_recommendations(
                db=db,
                user_id=current_user.id,
                ai_result=ai_result,
                source=source
            )
            
            return {
                "wardrobe_outfits": ai_result.wardrobe_outfits,
                "store_outfits": ai_result.store_outfits,
                "source": source
            }
        
        return None
        
    except Exception as e:
        logger.exception(f"[AI] 生成 AI 搭配推薦失敗: {str(e)}")
        return None


async def _save_daily_recommendations(
    db: Session,
    user_id: str,
    ai_result: Any,
    source: str
) -> None:
    """將 AI 推薦結果保存到 recommendations 表"""
    try:
        today = datetime.now(timezone.utc).date()
        expires_at = datetime.combine(today + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)
        
        # 檢查今日是否已有推薦記錄
        existing = db.query(Recommendation).filter(
            and_(
                Recommendation.user_id == user_id,
                Recommendation.kind == 'daily_inactive',
                Recommendation.created_at >= datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            )
        ).first()
        
        payload = {
            "wardrobe_outfits": [outfit.dict() for outfit in ai_result.wardrobe_outfits],
            "store_outfits": [outfit.dict() for outfit in ai_result.store_outfits],
            "generated_by": source,
            "generation_date": today.isoformat()
        }
        
        if existing:
            # 更新現有記錄
            existing.payload = payload
            existing.updated_at = datetime.now(timezone.utc)
            logger.info(f"[AI] 更新現有 daily_inactive 推薦記錄 (ID: {existing.id})")
        else:
            # 新建記錄
            new_rec = Recommendation(
                user_id=user_id,
                kind='daily_inactive',
                payload=payload,
                expires_at=expires_at
            )
            db.add(new_rec)
            logger.info(f"[AI] 新建 daily_inactive 推薦記錄")
        
        db.commit()
        
    except Exception as e:
        logger.exception(f"[AI] 保存推薦記錄失敗: {str(e)}")
        db.rollback()


@router.post("/wardrobe/ai")
async def get_ai_outfit_recommendations(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """
    互動式 AI 搭配建議 API
    根據用戶請求即時生成穿搭推薦（不保存到資料庫）
    """
    try:
        logger.info(f"[AI Interactive] 收到互動式 AI 搭配請求，用戶: {current_user.id}")
        
        user_request = request.get("user_request", "推薦穿搭")
        today_main_color = request.get("today_main_color", "中性")
        
        # 獲取用戶所有衣物
        all_wardrobe_items = (
            db.query(WardrobeItem)
            .filter(WardrobeItem.user_id == current_user.id)
            .all()
        )
        
        if not all_wardrobe_items:
            return {
                "success": False,
                "message": "您的衣櫃目前是空的，請先新增一些衣物！",
                "wardrobe_outfits": [],
                "store_outfits": []
            }
        
        # 準備衣櫃資料
        wardrobe_data = []
        for item in all_wardrobe_items:
            raw_category = getattr(item, "category", None)
            category_str = raw_category.value if hasattr(raw_category, "value") else str(raw_category)
            
            # 計算未穿天數
            now = datetime.now(timezone.utc)
            last_worn = getattr(item, "last_worn_at", None) or getattr(item, "created_at", None)
            days_inactive = (now - last_worn).days if last_worn else 0
            
            wardrobe_data.append({
                "id": str(item.id),
                "name": item.name or f"{category_str}_{item.id}",
                "category": map_category(category_str),
                "color": item.color or "未知",
                "color_family5": map_color_to_family(item.color),
                "styles": normalise_styles(item.style),
                "source": "wardrobe",
                "last_worn_days": days_inactive,
                "image_url": getattr(item, "cover_image_url", "")
            })
        
        # 準備 Style Shop 資料
        store_service = get_store_service()
        user_gender = "women"  # 預設女生
        if hasattr(current_user, "gender"):
            user_gender = "women" if current_user.gender in ["female", "女", "女生"] else "men"
        
        store_data = []
        store_items = store_service.get_items(gender=user_gender, limit=15)
        for store_item in store_items:
            store_data.append({
                "id": str(store_item.get("id", "")),
                "name": store_item.get("name", ""),
                "category": map_category(store_item.get("category", "")),
                "color": store_item.get("color", ""),
                "color_family5": map_color_to_family(store_item.get("color", "")),
                "styles": normalise_styles(store_item.get("style", "")),
                "source": "store",
                "price": store_item.get("price"),
                "purchaseUrl": store_item.get("purchaseUrl")
            })
        
        # 獲取天氣資訊
        weather_service = WeatherService()
        weather_info = await weather_service.get_weather(city="Taoyuan")
        
        # 建構 AI 請求負載
        payload = build_outfit_payload(
            wardrobe_items=wardrobe_data,
            store_items=store_data,
            user_request=user_request,
            today_main_color=today_main_color,
            gender=user_gender,
            weather=weather_info
        )
        
        # 呼叫 AI 服務
        def fallback_builder():
            return outfit_planner_ai_service.build_rule_based_plan(payload)
        
        ai_result, source, raw_text = outfit_planner_ai_service.generate_plan(
            payload, fallback_builder=fallback_builder
        )
        
        logger.info(f"[AI Interactive] 搭配生成完成，來源: {source}")
        
        if ai_result:
            return {
                "success": True,
                "message": "AI 搭配推薦生成成功！",
                "wardrobe_outfits": [outfit.dict() for outfit in ai_result.wardrobe_outfits],
                "store_outfits": [outfit.dict() for outfit in ai_result.store_outfits],
                "source": source,
                "weather": weather_info
            }
        else:
            return {
                "success": False,
                "message": "AI 搭配生成失敗，請稍後再試",
                "wardrobe_outfits": [],
                "store_outfits": []
            }
        
    except Exception as e:
        logger.exception(f"[AI Interactive] 互動式 AI 搭配失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI 搭配服務錯誤: {str(e)}")


@router.get("/daily-colors")
async def get_daily_color_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """
    本日主打色 - 五色系推薦
    為每個色系產生一組穿搭推薦
    """
    try:
        logger.info(f"[Daily Colors] 產生本日主打色推薦，用戶: {current_user.id}")
        
        # 五個色系
        COLOR_SYSTEMS = ["中性", "卡其棕", "藍", "紅粉", "綠"]
        PALETTE_MAP = {
            "中性": "neutral",
            "卡其棕": "khaki",
            "藍": "blue",
            "紅粉": "pink",
            "綠": "green"
        }
        
        # 30 天未穿衣物 ID，用於標記基準單品
        inactive_ids = {item.id for item in inactive_base_items}
        
        # 獲取用戶衣櫃
        wardrobe_items = (
            db.query(WardrobeItem)
            .filter(WardrobeItem.user_id == current_user.id)
            .all()
        )
        
        # 獲取天氣資訊
        weather_service = WeatherService()
        weather_info = await weather_service.get_weather(city="Taoyuan")
        
        # 用戶性別
        user_gender = normalise_gender_from_user(current_user, db=db)

        # 為每個色系產生推薦
        color_recommendations = {}
        store_service = get_store_service()
        
        for color_name in COLOR_SYSTEMS:
            palette_key = PALETTE_MAP[color_name]
            
            # 過濾該色系的衣櫃商品
            color_wardrobe = [
                item for item in wardrobe_items
                if map_color_to_family(item.color) == color_name
            ]
            
            # 獲取該色系的店家商品
            store_items = store_service.get_items(
                gender=user_gender,
                palette=palette_key,
                limit=6
            )
            
            # 準備資料
            wardrobe_data = []
            for item in color_wardrobe[:5]:  # 最多5件
                raw_category = getattr(item, "category", None)
                category_str = raw_category.value if hasattr(raw_category, "value") else str(raw_category)
                
                wardrobe_data.append({
                    "id": str(item.id),
                    "name": item.name or f"{category_str}_{item.id}",
                    "category": map_category(category_str),
                    "color": item.color or color_name,
                    "color_family5": color_name,
                    "styles": normalise_styles(item.style),
                    "source": "wardrobe",
                    "image_url": getattr(item, "cover_image_url", "")
                })
            
            # 準備店家資料
            store_data = []
            for store_item in store_items:
                store_data.append({
                    "id": store_item.get("id"),
                    "productId": store_item.get("productId"),
                    "name": store_item.get("name", ""),
                    "category": map_category(store_item.get("category", "")),
                    "color": color_name,
                    "color_family5": color_name,
                    "styles": [],
                    "source": "store",
                    "imageUrl": store_item.get("imageUrl"),
                    "purchaseUrl": store_item.get("purchaseUrl")
                })
            
            # 合併推薦（衣櫃 + 店家）
            color_recommendations[palette_key] = {
                "colorName": color_name,
                "paletteKey": palette_key,
                "wardrobeItems": wardrobe_data,
                "storeItems": store_data,
                "totalItems": len(wardrobe_data) + len(store_data)
            }
        
        # 挑選「今日主色」
        today_main_color = _select_today_main_color(
            color_recommendations,
            wardrobe_items,
            weather_info
        )
        
        logger.info(f"[Daily Colors] 今日主色: {today_main_color}")
        
        return {
            "todayMainColor": today_main_color,
            "colorRecommendations": color_recommendations,
            "weather": weather_info
        }
        
    except Exception as e:
        logger.exception(f"[Daily Colors] 產生本日主打色推薦失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"產生色系推薦失敗: {str(e)}")


def _select_today_main_color(
    color_recommendations: Dict[str, Any],
    wardrobe_items: List[WardrobeItem],
    weather_info: Optional[Dict[str, Any]]
) -> str:
    """
    挑選今日主色的邏輯
    
    評分規則：
    1. 衣櫃匹配度（該色系有多少衣物）
    2. 天氣適配度（溫度影響色系選擇）
    3. 季節性（當前月份）
    """
    scores = {}
    
    for palette_key, data in color_recommendations.items():
        score = 0
        
        # 1. 衣櫃匹配度（20-40分）
        wardrobe_count = len(data.get("wardrobeItems", []))
        score += min(wardrobe_count * 10, 40)
        
        # 2. 店家商品豐富度（10-30分）
        store_count = len(data.get("storeItems", []))
        score += min(store_count * 5, 30)
        
        # 3. 天氣適配度（0-30分）
        if weather_info:
            temp = weather_info.get("temperature", 20)
            if palette_key == "khaki" and temp < 15:
                score += 30  # 冷天偏暖色
            elif palette_key == "blue" and temp > 25:
                score += 30  # 熱天偏涼色
            elif palette_key == "neutral":
                score += 20  # 中性色百搭
        
        scores[palette_key] = score
    
    # 選擇得分最高的色系
    if scores:
        today_color = max(scores, key=scores.get)
        logger.info(f"[Today Color] 色系評分: {scores}, 選中: {today_color}")
        return today_color
    
    return "neutral"  # 預設中性


def _build_seed_store_outfit_for_family(
    seed: WardrobeItem,
    gender: str,
    family_key: str,
    store_service,
    random_seed: int,
) -> Optional[Dict[str, Any]]:
    """給定一件 seed 衣物，為指定三色系產生一套「seed + 商店商品」的穿搭。"""
    random.seed(random_seed)

    raw_cat = getattr(seed, "category", None)
    if hasattr(raw_cat, "value"):
        raw_cat = raw_cat.value

    db_uri = getattr(seed, "cover_image_url", None) or ""
    main_img = resolve_image_url(db_uri) if db_uri else ""

    main_name = getattr(seed, "name", "") or (raw_cat or "")

    main_item = {
        "itemId": str(seed.id),
        "source": "wardrobe",
        "name": main_name,
        "category": raw_cat,
        "imageUrl": main_img,
        "purchaseUrl": None,
    }

    # 三色系 -> 店家 palette 對應
    family_to_palettes = {
        "neutral": ["neutral"],
        "earth": ["khaki", "pink"],
        "cool": ["blue", "green"],
    }
    palette_keys = family_to_palettes.get(family_key, ["neutral"])

    # 根據 seed 類別挑選適合的店家類別
    store_categories: List[str] = []
    if raw_cat == "上衣":
        store_categories = ["褲子", "裙子", "包包"]
    elif raw_cat in ["褲子", "裙子"]:
        store_categories = ["上衣", "包包"]
    elif raw_cat == "外套":
        store_categories = ["上衣", "褲子", "裙子"]
    else:
        store_categories = ["上衣", "褲子", "裙子", "包包"]

    store_candidates: List[Dict[str, Any]] = []
    for pal in palette_keys:
        for cat in store_categories:
            items = store_service.get_items(
                gender=gender,
                palette=pal,
                category=cat,
                limit=3,
            )
            if items:
                store_candidates.extend(items)

    # 去重
    seen_ids = set()
    unique_candidates: List[Dict[str, Any]] = []
    for it in store_candidates:
        sid = str(it.get("id"))
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        unique_candidates.append(it)

    if not unique_candidates:
        return None

    selected: List[Dict[str, Any]] = []

    # 特殊規則：若 seed 是「上衣」，優先保證至少有一件下身，再搭配包包/其他
    if raw_cat == "上衣":
        bottom_candidates = [it for it in unique_candidates if it.get("category") in ["褲子", "裙子"]]
        bag_candidates = [it for it in unique_candidates if it.get("category") == "包包"]
        other_candidates = [
            it
            for it in unique_candidates
            if it not in bottom_candidates and it not in bag_candidates
        ]

        # 為了在同一 random_seed 下仍有隨機性，對各組別個別洗牌
        random.shuffle(bottom_candidates)
        random.shuffle(bag_candidates)
        random.shuffle(other_candidates)

        # 1) 先選一件下身
        if bottom_candidates:
            selected.append(bottom_candidates[0])

        # 2) 再選一件包包；若沒有包包，改選其他類別
        if len(selected) < 2:
            if bag_candidates:
                selected.append(bag_candidates[0])
            elif other_candidates:
                selected.append(other_candidates[0])

        # 若仍然只有 1 件，且還有其他候選，補一件不同來源（避免再補到包包）
        if len(selected) < 2 and len(unique_candidates) > len(selected):
            remaining = [
                it
                for it in unique_candidates
                if it not in selected and it.get("category") != "包包"
            ]
            if remaining:
                random.shuffle(remaining)
                selected.append(remaining[0])

    elif raw_cat == "外套":
        # 外套：至少一件下身（褲子/裙子；女生再加洋裝），再搭配上衣或其他
        bottom_like_cats = ["褲子", "裙子"]
        if gender == "women":
            bottom_like_cats = ["褲子", "裙子", "洋裝"]

        bottom_candidates = [it for it in unique_candidates if it.get("category") in bottom_like_cats]
        top_candidates = [it for it in unique_candidates if it.get("category") == "上衣"]
        other_candidates = [
            it
            for it in unique_candidates
            if it not in bottom_candidates and it not in top_candidates
        ]

        random.shuffle(bottom_candidates)
        random.shuffle(top_candidates)
        random.shuffle(other_candidates)

        # 1) 先選一件下身 / 洋裝
        if bottom_candidates:
            selected.append(bottom_candidates[0])

        # 2) 再選一件上衣；若沒有上衣，改選其他類別
        if len(selected) < 2:
            if top_candidates:
                selected.append(top_candidates[0])
            elif other_candidates:
                selected.append(other_candidates[0])

        # 3) 若仍然只有 1 件，且還有其他候選，補一件「非上衣」
        if len(selected) < 2 and len(unique_candidates) > len(selected):
            remaining = [it for it in unique_candidates if it not in selected]
            # 若已經選過上衣，就不要再選第二件上衣
            if any(s.get("category") == "上衣" for s in selected):
                remaining = [it for it in remaining if it.get("category") != "上衣"]
            if remaining:
                random.shuffle(remaining)
                selected.append(remaining[0])

    elif raw_cat == "洋裝":
        # 洋裝：避免再搭上衣，專注外套 / 包包 / 其他配件
        non_top_candidates = [it for it in unique_candidates if it.get("category") != "上衣"]
        if non_top_candidates:
            bag_candidates = [it for it in non_top_candidates if it.get("category") == "包包"]
            other_candidates = [it for it in non_top_candidates if it.get("category") != "包包"]
            random.shuffle(bag_candidates)
            random.shuffle(other_candidates)
            selected = []
            if other_candidates:
                selected.append(other_candidates[0])
            if len(selected) < 2:
                if bag_candidates:
                    selected.append(bag_candidates[0])
                elif len(other_candidates) > 1:
                    selected.append(other_candidates[1])
        else:
            # 若全部都是上衣，就不強行推薦店家商品（只保留 seed 洋裝）
            selected = []

    else:
        # 其他類別維持原本行為：隨機選最多 2 件
        random.shuffle(unique_candidates)
        selected = unique_candidates[:2]

    items: List[Dict[str, Any]] = [main_item]
    for s in selected:
        items.append({
            "itemId": str(s.get("id")),
            "source": "store",
            "name": s.get("name", ""),
            "category": s.get("category", ""),
            "imageUrl": s.get("imageUrl"),
            "purchaseUrl": s.get("purchaseUrl"),
        })

    # 全域規則 1：同一套商店搭配最多只出現一件「上衣」
    filtered_items: List[Dict[str, Any]] = []
    seen_top = False
    for it in items:
        if it.get("category") == "上衣":
            if seen_top:
                continue
            seen_top = True
        filtered_items.append(it)
    items = filtered_items

    if len(items) < 2:
        return None

    cfg = COLOR_FAMILY3_CONFIG.get(family_key, {"name": family_key})
    title = f"{cfg.get('name', family_key)} x {main_name} 商店搭配"
    outfit_id_suffix = str(seed.id)[-6:]

    return {
        "id": f"{family_key}_extra_store_{outfit_id_suffix}",
        "seedItemId": str(seed.id),
        "colorFamily": family_key,
        "title": title,
        "reason": "以 30 天未穿的衣物為核心，搭配 Style Shop 商品，為此色系多提供一套靈感穿搭。",
        "items": items,
    }


@router.get("/daily-color-outfits")
async def get_daily_color_outfits(
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """
    本日主打色 + 色系推薦（3 色系：neutral / earth / cool）

    - 以 30 天未穿的 3 件 seed 衣物為核心
    - 今日推薦的 3 套穿搭由 seed 直接生成（/today-recommend 使用）
    - 本日主打色頁面：每個色系在原有 seed-based outfit 基礎上，
      會額外增加 1 套「seed + 商店商品」的穿搭，目標是每色系最多顯示 2 套
    - mainColorFamily 由 3 件 seed 的 family 多數決決定
    """
    try:
        plan = await _build_today_seed_plan(db=db, current_user=current_user)

        main_family = plan["mainColorFamily"]
        seed_meta = plan.get("seedItems", [])

        # 構建 seedId -> WardrobeItem 對照表
        seed_ids = [m["id"] for m in seed_meta if m.get("id")]
        seed_items_map: Dict[str, WardrobeItem] = {}
        if seed_ids:
            seed_objs = (
                db.query(WardrobeItem)
                .filter(WardrobeItem.user_id == current_user.id)
                .filter(WardrobeItem.id.in_(seed_ids))
                .all()
            )
            for s in seed_objs:
                seed_items_map[str(s.id)] = s

        store_service = get_store_service()

        # 建立當日固定隨機種子，確保同一天結果穩定
        try:
            today_int = int(str(plan["date"]).replace("-", ""))
        except Exception:
            today_int = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
        try:
            user_seed_part = int(str(current_user.id).replace("-", "")[:8], 16)
        except Exception:
            user_seed_part = 0
        daily_seed = today_int + user_seed_part

        families_payload: List[Dict[str, Any]] = []

        for fam_index, key in enumerate(COLOR_FAMILY3_PRIORITY):
            cfg = COLOR_FAMILY3_CONFIG.get(key, {"name": key, "palette": []})

            # 先拿這個色系原本的 seed-based outfit（若有）
            existing_family_outfits = [
                o for o in plan["outfits"]
                if o.get("colorFamily") == key
            ]

            family_outfits: List[Dict[str, Any]] = []

            primary_seed_id: Optional[str] = None

            if existing_family_outfits:
                # 保留第一套 seed-based outfit
                first_outfit = existing_family_outfits[0]
                family_outfits.append(first_outfit)
                primary_seed_id = first_outfit.get("seedItemId")
            else:
                # 沒有 seed-based outfit，改用 seed meta 中屬於該 family 的 id
                for m in seed_meta:
                    if m.get("colorFamily") == key:
                        primary_seed_id = m.get("id")
                        break
                # 若仍然找不到，退回第一個 seed 作為基準
                if not primary_seed_id and seed_meta:
                    primary_seed_id = seed_meta[0].get("id")

            # 針對這個 family 額外產生 1 套「seed + 商店」穿搭
            if primary_seed_id:
                seed_obj = seed_items_map.get(primary_seed_id)
                if seed_obj is None:
                    seed_obj = (
                        db.query(WardrobeItem)
                        .filter(WardrobeItem.user_id == current_user.id)
                        .filter(WardrobeItem.id == primary_seed_id)
                        .first()
                    )
                    if seed_obj:
                        seed_items_map[primary_seed_id] = seed_obj

                if seed_obj:
                    rnd_seed = daily_seed + fam_index * 10
                    extra = _build_seed_store_outfit_for_family(
                        seed=seed_obj,
                        gender=plan["gender"],
                        family_key=key,
                        store_service=store_service,
                        random_seed=rnd_seed,
                    )
                    if extra:
                        family_outfits.append(extra)

            # 最多保留 2 套，避免前端列表過長
            if len(family_outfits) > 2:
                family_outfits = family_outfits[:2]

            families_payload.append({
                "key": key,
                "name": cfg["name"],
                "colors": cfg["palette"],
                "isMain": (key == main_family),
                "outfits": family_outfits,
            })

        main_cfg = COLOR_FAMILY3_CONFIG.get(main_family, {"name": main_family, "palette": []})

        logger.info(
            "[Daily Color Outfits] 返回本日主打色: date=%s user_id=%s gender=%s main_family=%s",
            plan["date"],
            getattr(current_user, "id", None),
            plan["gender"],
            main_family,
        )

        return {
            "date": plan["date"],
            "gender": plan["gender"],
            "mainColorFamily": main_family,
            "mainColorName": main_cfg["name"],
            "mainColorPalette": main_cfg["palette"],
            "families": families_payload,
        }

    except Exception as e:
        logger.exception(f"[Daily Color Outfits] 生成失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成每日色系穿搭失敗: {str(e)}")


async def _generate_color_outfits(
    color_name: str,
    wardrobe_items: List[Dict],
    store_items: List[Dict],
    weather_info: Optional[Dict],
    target_count: int = 3
) -> List[Dict[str, Any]]:
    """
    為單一色系生成指定數量的穿搭
    """
    outfits = []
    
    # 如果沒有足夠的商品，返回空列表
    all_items = wardrobe_items + store_items
    if len(all_items) < 2:
        return []
    
    # 簡單規則：隨機組合生成穿搭
    random.shuffle(all_items)
    
    for i in range(min(target_count, len(all_items) // 2)):
        # 選擇 2-3 件商品組成一套
        items_in_outfit = []
        used_categories = set()
        
        for item in all_items:
            if len(items_in_outfit) >= 3:
                break
            
            category = item.get("category", "")
            if category not in used_categories:
                items_in_outfit.append({
                    "itemId": item.get("id"),
                    "source": item.get("source"),
                    "name": item.get("name"),
                    "category": category,
                    "imageUrl": item.get("image_url") or item.get("imageUrl"),
                    "purchaseUrl": item.get("purchaseUrl") if item.get("source") == "store" else None
                })
                used_categories.add(category)
        
        if len(items_in_outfit) >= 2:
            outfit = {
                "id": f"{color_name.lower()}_outfit_{i+1}",
                "title": f"{color_name}色系穿搭 #{i+1}",
                "items": items_in_outfit,
                "mainColorFamily5": color_name,
                "styles": ["日常"],
                "reason": f"以{color_name}色為主調的搭配建議"
            }
            outfits.append(outfit)
    
    return outfits


def _select_main_color_for_daily_palettes(
    records: List[DailyColorOutfit],
    weather_info: Optional[Dict[str, Any]]
) -> str:
    """
    從五個色系中選出今日主色
    """
    scores = {}
    
    for record in records:
        score = 0
        
        # 1. 穿搭數量
        outfit_count = len(record.outfits_json)
        score += outfit_count * 10
        
        # 2. 天氣適配
        if weather_info:
            temp = weather_info.get("temperature", 20)
            if record.color_family == "khaki" and temp < 15:
                score += 30
            elif record.color_family == "blue" and temp > 25:
                score += 30
            elif record.color_family == "neutral":
                score += 20
        
        scores[record.color_family] = score
    
    if scores:
        return max(scores, key=scores.get)
    
    return "neutral"


@router.get("/today-recommend")
async def get_today_recommend(
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """今日推薦：
    以「超過 30 天未穿」的 3 件 seed 衣物為核心，各生成一套穿搭。

    - 一定會選出最多 3 件 seed（A/B/C），每套 outfit 必含其中一件
    - 每套 outfit 會標記 seedItemId 與 colorFamily（三色系：neutral/earth/cool）
    - mainColorFamily 由三件 seed 的 family 多數決決定，平手時依優先順序
    """
    try:
        plan = await _build_today_seed_plan(db=db, current_user=current_user)

        main_family = plan["mainColorFamily"]
        cfg = COLOR_FAMILY3_CONFIG.get(main_family, {
            "name": main_family,
            "palette": [],
        })

        logger.info(
            "[Today Recommend] 返回今日推薦: date=%s user_id=%s gender=%s main_family=%s seed_count=%s",
            plan["date"],
            getattr(current_user, "id", None),
            plan["gender"],
            main_family,
            len(plan.get("seedItems", [])),
        )

        return {
            "date": plan["date"],
            "gender": plan["gender"],
            "mainColorFamily": main_family,
            "mainColorName": cfg["name"],
            "mainColorPalette": cfg["palette"],
            "outfits": plan["outfits"],
        }

    except Exception as e:
        logger.exception(f"[Today Recommend] 取得失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"取得今日推薦失敗: {str(e)}")


async def _get_30_days_inactive_items(
    db: Session,
    user_id: int,
    limit: int = 3
) -> List[WardrobeItem]:
    """
    取得超過 30 天未穿的衣物作為今日推薦基準（seed items）

    規則：
    - 只看當前使用者的 WardrobeItem
    - 若 last_worn_at 存在，使用它；否則退回 created_at
    - daysInactive = (now - base_dt).days
    - 先過濾出 daysInactive >= 30 的衣物
    - 依 |daysInactive - 30| 由小到大排序，取前 limit 件
    - 若沒有任何 >=30 天未穿衣物，則退回所有衣物中 daysInactive 最大的前 limit 件
    """
    now = datetime.now(timezone.utc)

    # 查詢使用者所有衣物
    all_items: List[WardrobeItem] = (
        db.query(WardrobeItem)
        .filter(WardrobeItem.user_id == user_id)
        .all()
    )

    if not all_items:
        return []

    def _calc_days_inactive(item: WardrobeItem) -> int:
        """計算單件衣物距今未穿天數。

        支援以下型別：
        - timezone-aware datetime
        - naive datetime（自動補上 UTC）
        - date 物件（year/month/day）
        其他型別則視為極大值（代表很久沒穿）。
        """
        base_dt = getattr(item, "last_worn_at", None) or getattr(item, "created_at", None)
        if not base_dt:
            return 9999

        # datetime (aware / naive)
        if isinstance(base_dt, datetime):
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=timezone.utc)
        # date-like（沒有時間資訊）
        elif hasattr(base_dt, "year") and hasattr(base_dt, "month") and hasattr(base_dt, "day"):
            base_dt = datetime(base_dt.year, base_dt.month, base_dt.day, tzinfo=timezone.utc)
        else:
            return 9999

        return (now - base_dt).days

    items_with_days: List[Dict[str, Any]] = []
    for it in all_items:
        days_inactive = _calc_days_inactive(it)
        items_with_days.append({
            "item": it,
            "daysInactive": days_inactive,
        })

    # 先挑出 >=30 天未穿的
    over_30 = [x for x in items_with_days if x["daysInactive"] >= 30]

    def _sort_key_close_to_30(x: Dict[str, Any]) -> int:
        return abs(x["daysInactive"] - 30)

    if over_30:
        over_30.sort(key=_sort_key_close_to_30)
        selected = over_30[:limit]
    else:
        # 沒有滿足 30 天條件，直接選擇 daysInactive 最大的幾件
        items_with_days.sort(key=lambda x: x["daysInactive"], reverse=True)
        selected = items_with_days[:limit]

    return [x["item"] for x in selected]


async def _build_today_seed_plan(
    db: Session,
    current_user: User,
) -> Dict[str, Any]:
    """建立今日推薦 / 本日主打色共用的 seed-based 計畫。

    - 取得 3 件 30 天未穿的 seed items
    - 為每個 seed 生成一套 outfit（必含該 seed）
    - 依 seed 的顏色 family（3 色系）決定 mainColorFamily
    """
    today = datetime.now(timezone.utc).date()
    date_str = str(today)
    gender = normalise_gender_from_user(current_user, db=db)

    # 取得 seed items（最多 3 件）
    seed_items: List[WardrobeItem] = await _get_30_days_inactive_items(
        db=db,
        user_id=current_user.id,
        limit=3,
    )

    if not seed_items:
        return {
            "date": date_str,
            "gender": gender,
            "mainColorFamily": "neutral",
            "seedItems": [],
            "outfits": [],
        }

    # 取得使用者全部衣物（用於搭配）
    all_items: List[WardrobeItem] = (
        db.query(WardrobeItem)
        .filter(WardrobeItem.user_id == current_user.id)
        .all()
    )

    store_service = get_store_service()

    # 當日種子，讓同一天同一使用者的結果穩定
    try:
        user_seed_part = int(str(current_user.id).replace("-", "")[:8], 16)
    except Exception:
        user_seed_part = 0
    daily_seed = int(today.strftime("%Y%m%d")) + user_seed_part

    outfits: List[Dict[str, Any]] = []
    seed_meta: List[Dict[str, Any]] = []

    for idx, seed in enumerate(seed_items):
        fam3 = map_color_to_3_family(getattr(seed, "color", None))

        # 保存 seed 基本資訊
        seed_meta.append({
            "id": str(seed.id),
            "colorFamily": fam3,
        })

        # 構建單一 seed 的 outfit
        rnd_seed = daily_seed + idx
        random.seed(rnd_seed)

        # 1) 主要衣物（seed 本身）
        raw_cat = getattr(seed, "category", None)
        if hasattr(raw_cat, "value"):
            raw_cat = raw_cat.value

        db_uri = getattr(seed, "cover_image_url", None) or ""
        main_img = resolve_image_url(db_uri) if db_uri else ""

        main_item = {
            "itemId": str(seed.id),
            "source": "wardrobe",
            "name": getattr(seed, "name", "") or (raw_cat or ""),
            "category": raw_cat,
            "imageUrl": main_img,
            "purchaseUrl": None,
        }

        # 2) 衣櫃搭配建議
        wardrobe_suggestions = get_clothing_suggestions(seed, all_items, seed=rnd_seed)
        for sug in wardrobe_suggestions:
            sug["source"] = "wardrobe"
            sug["purchaseUrl"] = None

        # 3) 店家商品搭配（依 seed 類別）
        item_category = raw_cat or ""
        store_items: List[Dict[str, Any]] = []

        if item_category == "上衣":
            store_items = store_service.get_items(gender=gender, category="褲子", limit=2)
            if not store_items:
                store_items = store_service.get_items(gender=gender, category="包包", limit=2)
        elif item_category in ["褲子", "裙子"]:
            store_items = store_service.get_items(gender=gender, category="上衣", limit=2)
        elif item_category == "外套":
            store_items = store_service.get_items(gender=gender, category="上衣", limit=1)

        store_suggestions: List[Dict[str, Any]] = []
        if store_items:
            # 最多挑 1~2 件店家商品
            random.shuffle(store_items)
            for s in store_items[:2]:
                store_suggestions.append({
                    "itemId": str(s.get("id")),
                    "source": "store",
                    "name": s.get("name", ""),
                    "category": map_category(s.get("category", "")),
                    "imageUrl": s.get("imageUrl"),
                    "purchaseUrl": s.get("purchaseUrl"),
                })

        # 組合所有 items：seed + 衣櫃搭配 + 店家搭配
        items: List[Dict[str, Any]] = [main_item]

        for sug in wardrobe_suggestions:
            items.append({
                "itemId": sug.get("id"),
                "source": sug.get("source", "wardrobe"),
                "name": sug.get("name"),
                "category": sug.get("category"),
                "imageUrl": sug.get("imageUrl"),
                "purchaseUrl": None,
            })

        items.extend(store_suggestions)

        # 最多保留 3 件（主件 + 1~2 搭配）
        if len(items) > 3:
            items = items[:3]

        def _canonical_category(cat):
            if not cat:
                return ""
            try:
                return map_category(cat)
            except Exception:
                return ""

        if raw_cat in ["上衣", "褲子", "裙子"]:
            top_index = None
            bottom_index = None
            for i, it in enumerate(items):
                cat_norm = _canonical_category(it.get("category"))
                if top_index is None and cat_norm == "top":
                    top_index = i
                if bottom_index is None and cat_norm == "bottom":
                    bottom_index = i

            if raw_cat == "上衣" and bottom_index is not None:
                top_item = items[0]
                bottom_item = items[bottom_index]
                items = [top_item, bottom_item]
            elif raw_cat in ["褲子", "裙子"] and top_index is not None:
                bottom_item = items[0]
                top_item = items[top_index]
                items = [top_item, bottom_item]

        # 全域規則 2：任何情況下，同一套 seed-based 穿搭最多只出現一件「top」
        seen_top = False
        filtered_items: List[Dict[str, Any]] = []
        for it in items:
            cat_norm = _canonical_category(it.get("category"))
            if cat_norm == "top":
                if seen_top:
                    continue
                seen_top = True
            filtered_items.append(it)
        items = filtered_items

        outfits.append({
            "id": f"seed_outfit_{idx+1}",
            "seedItemId": str(seed.id),
            "colorFamily": fam3,
            "title": f"以 {getattr(seed, 'name', '') or (raw_cat or '單品')} 為主的穿搭 #{idx+1}",
            "reason": "以 30 天未穿的衣物為核心，幫你重新搭配出可以穿出門的一套。",
            "items": items,
        })

    # 決定 mainColorFamily：以 seedItems 的 family 次數為主，多數決；平手則依優先順序
    counts: Dict[str, int] = {}
    for meta in seed_meta:
        fam = meta["colorFamily"]
        counts[fam] = counts.get(fam, 0) + 1

    if counts:
        # 先找出最高出現次數
        max_count = max(counts.values())
        candidates = [fam for fam, c in counts.items() if c == max_count]

        # 依 COLOR_FAMILY3_PRIORITY 決定優先順序
        for fam in COLOR_FAMILY3_PRIORITY:
            if fam in candidates:
                main_family = fam
                break
        else:
            main_family = "neutral"
    else:
        main_family = "neutral"

    return {
        "date": date_str,
        "gender": gender,
        "mainColorFamily": main_family,
        "seedItems": seed_meta,
        "outfits": outfits,
    }


def _build_daily_color_outfits_response(
    records: List[DailyColorOutfit],
    date,
    gender: str
) -> Dict[str, Any]:
    """
    組裝回傳格式（新架構）
    """
    # 色系設定
    COLOR_CONFIG = {
        "neutral": {"name": "中性", "colors": ["#F5F5F5", "#D3D3D3", "#808080", "#2F4F4F"]},
        "khaki": {"name": "卡其棕", "colors": ["#F0E68C", "#DAA520", "#CD853F", "#8B4513"]},
        "blue": {"name": "藍", "colors": ["#87CEEB", "#4169E1", "#00008B", "#000080"]},
        "pink": {"name": "紅粉", "colors": ["#FFB6C1", "#FF69B4", "#FF1493", "#C71585"]},
        "green": {"name": "綠", "colors": ["#90EE90", "#32CD32", "#228B22", "#006400"]}
    }
    
    families = []
    
    for record in records:
        config = COLOR_CONFIG.get(record.color_family, {"name": record.color_family, "colors": []})

        # 深拷貝並修正舊資料中的圖片 URL（可能仍為 gs://）
        processed_outfits: List[Dict[str, Any]] = []
        for outfit in record.outfits_json or []:
            items = []
            for item in outfit.get("items", []):
                # 取得原始圖片欄位
                raw_img = item.get("imageUrl") or item.get("image_url") or ""
                fixed_img = resolve_image_url(raw_img) if raw_img else ""

                new_item = dict(item)
                new_item["imageUrl"] = fixed_img
                items.append(new_item)

            new_outfit = dict(outfit)
            new_outfit["items"] = items
            processed_outfits.append(new_outfit)
        
        families.append({
            "key": record.color_family,
            "name": config["name"],
            "colors": config["colors"],
            "isMain": record.is_main_color,
            "outfits": processed_outfits,
        })
    
    return {
        "date": str(date),
        "gender": gender,
        "families": families
    }
