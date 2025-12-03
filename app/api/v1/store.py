"""
店家商品 API
提供店家商品查詢功能
"""
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, Literal, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import requests
from io import BytesIO
from rembg import remove
from PIL import Image

from app.services.store_items import get_store_service
from app.core.db import get_db
from app.models.auth import User
from app.models.wardrobe import WardrobeItem, CategoryEnum
from app.api.v1.auth import get_current_user
from app.services.storage import upload_file_to_gcs
import os

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/store",
    tags=["店家商品"],
)

# GCS Bucket 設定
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "smartclothes_wardrobe")


@router.get("/items")
def list_store_items(
    gender: Literal["women", "men"] = Query(..., description="性別篩選"),
    palette: Optional[str] = Query(None, description="色系篩選（neutral/khaki/blue/pink/green）"),
    category: Optional[str] = Query(None, description="類別篩選"),
    limit: int = Query(12, ge=1, le=100, description="限制數量"),
) -> List[Dict[str, Any]]:
    """
    取得店家商品列表
    
    - **gender**: 性別（women/men）
    - **palette**: 色系（neutral/khaki/blue/pink/green）
    - **category**: 類別（上衣/褲子/裙子等）
    - **limit**: 限制回傳數量
    
    回傳欄位：
    - id: 商品 ID
    - name: 商品名稱
    - category: 類別
    - palette: 色系
    - imageUrl: 圖片 URL
    - gender: 性別
    - source: 來源（store）
    - purchaseUrl: 購買連結
    """
    try:
        store_service = get_store_service()
        items = store_service.get_items(
            gender=gender,
            palette=palette,
            category=category,
            limit=limit,
        )
        
        logger.info(f"[store] 查詢商品: gender={gender}, palette={palette}, category={category}, 回傳 {len(items)} 件")
        return items
    
    except Exception as e:
        logger.error(f"[store] 查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/palette/{color_family}")
def get_palette_items(
    color_family: str,
    gender: Literal["women", "men"] = Query(..., description="性別篩選"),
    limit: int = Query(12, ge=1, le=100, description="限制數量"),
) -> List[Dict[str, Any]]:
    """
    取得指定色系的商品
    
    - **color_family**: 色系（neutral/khaki/blue/pink/green）
    - **gender**: 性別（women/men）
    - **limit**: 限制回傳數量
    """
    try:
        store_service = get_store_service()
        items = store_service.get_items(
            gender=gender,
            palette=color_family,
            limit=limit,
        )
        
        logger.info(f"[store] 查詢色系商品: color_family={color_family}, gender={gender}, 回傳 {len(items)} 件")
        return items
    
    except Exception as e:
        logger.error(f"[store] 查詢色系商品失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/palettes")
def get_all_palettes(
    gender: Literal["women", "men"] = Query(..., description="性別篩選"),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    取得所有色系的商品（每個色系 4 件）
    
    用於「今日推薦」的其他色系靈感
    
    回傳格式：
    ```json
    {
        "neutral": [{...}, {...}],
        "khaki": [{...}, {...}],
        "blue": [{...}, {...}],
        ...
    }
    ```
    """
    try:
        store_service = get_store_service()
        result = store_service.get_items_by_palette_all(gender=gender)
        
        logger.info(f"[store] 取得所有色系商品: gender={gender}, 色系數={len(result)}")
        return result
    
    except Exception as e:
        logger.error(f"[store] 取得色系商品失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{product_id}/add-to-wardrobe")
async def add_store_item_to_wardrobe(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    將店家商品加入用戶衣櫥
    
    流程：
    1. 根據 product_id 查詢店家商品資訊
    2. 從 GCS 下載商品圖片（smartclothes-styleshop bucket）
    3. 上傳到用戶衣櫥 GCS（smartclothes_wardrobe bucket）
    4. 建立衣櫥資料庫記錄
    
    - **product_id**: 店家商品 ID
    
    回傳：
    - 新增的衣櫥商品資訊
    """
    try:
        # 1. 查詢店家商品
        store_service = get_store_service()
        all_items = store_service.get_items(limit=1000)  # 取得所有商品
        
        store_item = None
        for item in all_items:
            if item.get("id") == product_id or item.get("productId") == product_id:
                store_item = item
                break
        
        if not store_item:
            raise HTTPException(status_code=404, detail=f"找不到商品 ID: {product_id}")
        
        logger.info(f"[add-to-wardrobe] 找到店家商品: {store_item.get('name')}")
        
        # 2. 從 GCS 下載圖片
        image_url = store_item.get("imageUrl")
        if not image_url:
            raise HTTPException(status_code=400, detail="商品沒有圖片 URL")
        
        logger.info(f"[add-to-wardrobe] 下載圖片: {image_url}")
        
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_bytes = response.content
        except Exception as e:
            logger.error(f"[add-to-wardrobe] 下載圖片失敗: {e}")
            raise HTTPException(status_code=500, detail=f"下載圖片失敗: {str(e)}")
        
        # 3. 去背處理
        logger.info(f"[add-to-wardrobe] 開始去背處理...")
        try:
            # 將圖片轉為 PIL Image
            input_image = Image.open(BytesIO(image_bytes))
            
            # 使用 rembg 去背
            output_image = remove(input_image, alpha_matting=True)
            
            # 轉為 PNG bytes
            output_buffer = BytesIO()
            output_image.save(output_buffer, format="PNG")
            image_bytes = output_buffer.getvalue()
            
            logger.info(f"[add-to-wardrobe] 去背完成，圖片大小: {len(image_bytes)} bytes")
        except Exception as e:
            logger.warning(f"[add-to-wardrobe] 去背失敗，使用原圖: {e}")
            # 去背失敗時使用原圖
        
        # 4. 準備上傳到用戶衣櫥 GCS
        # 類別映射
        category_map = {
            "上衣": CategoryEnum.TOP,
            "褲子": CategoryEnum.PANTS,
            "裙子": CategoryEnum.SKIRT,
            "洋裝": CategoryEnum.DRESS,
            "外套": CategoryEnum.OUTER,
            "鞋子": CategoryEnum.SHOES,
            "帽子": CategoryEnum.HAT,
            "包包": CategoryEnum.BAG,
            "配件": CategoryEnum.ACCESSORY,
            "下身": CategoryEnum.PANTS,
        }
        
        category_gcs_map = {
            "上衣": "tops",
            "褲子": "bottoms",
            "裙子": "skirts",
            "洋裝": "dresses",
            "外套": "outerwear",
            "鞋子": "shoes",
            "帽子": "hats",
            "包包": "bags",
            "配件": "accessories",
            "下身": "bottoms",
        }
        
        item_category = store_item.get("category", "上衣")
        category_enum = category_map.get(item_category, CategoryEnum.TOP)
        category_gcs = category_gcs_map.get(item_category, "tops")
        
        # 建立 GCS 路徑: wardrobe/{user_id}/{category}/store_{product_id}.png（去背後使用 PNG）
        user_id_str = str(current_user.id)
        gcs_path = f"wardrobe/{user_id_str}/{category_gcs}/store_{product_id}.png"
        
        logger.info(f"[add-to-wardrobe] 上傳至: gs://{GCS_BUCKET_NAME}/{gcs_path}")
        
        # 5. 上傳到 GCS
        try:
            cover_url = upload_file_to_gcs(
                file_bytes=image_bytes,
                destination_blob_name=gcs_path,
                mime_type="image/png",
                bucket_name=GCS_BUCKET_NAME,
                public=False,
            )
            logger.info(f"[add-to-wardrobe] GCS 上傳成功: {cover_url}")
        except Exception as gcs_error:
            logger.error(f"[add-to-wardrobe] GCS 上傳失敗: {gcs_error}")
            raise HTTPException(status_code=500, detail=f"圖片上傳失敗: {str(gcs_error)}")
        
        # 6. 檢查是否已存在相同商品（避免重複加入）
        existing_item = db.query(WardrobeItem).filter(
            WardrobeItem.user_id == current_user.id,
            WardrobeItem.name == store_item.get("name"),
            WardrobeItem.category == category_enum,
        ).first()
        
        if existing_item:
            logger.info(f"[add-to-wardrobe] 商品已存在於衣櫥: {existing_item.id}")
            return {
                "message": "此商品已在您的衣櫥中",
                "item": {
                    "id": str(existing_item.id),
                    "name": existing_item.name,
                    "category": existing_item.category.value,
                    "color": existing_item.color,
                    "img": cover_url,
                    "source": "store",
                    "already_exists": True,
                }
            }
        
        # 7. 建立衣櫥資料庫記錄
        wardrobe_item = WardrobeItem(
            user_id=current_user.id,
            name=store_item.get("name", f"店家商品 {product_id}"),
            category=category_enum,
            color=store_item.get("palette", ""),
            cover_image_url=cover_url,
            tags=["品牌合作", "Style Shop"],
            attributes={"source": "store", "product_id": product_id, "bg_removed": True},
            brand="Style Shop",
            style=None,
            last_worn_at=datetime.now(timezone.utc),
        )
        
        db.add(wardrobe_item)
        db.commit()
        db.refresh(wardrobe_item)
        
        logger.info(f"[add-to-wardrobe] 成功加入衣櫥: {wardrobe_item.id}")
        
        return {
            "message": "成功加入衣櫥",
            "item": {
                "id": str(wardrobe_item.id),
                "name": wardrobe_item.name,
                "category": wardrobe_item.category.value,
                "color": wardrobe_item.color,
                "img": cover_url,
                "source": "store",
                "product_id": product_id,
                "already_exists": False,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[add-to-wardrobe] 加入衣櫥失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"加入衣櫥失敗: {str(e)}")
