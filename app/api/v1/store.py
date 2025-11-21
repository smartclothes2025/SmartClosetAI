"""
店家商品 API
提供店家商品查詢功能
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Literal, List, Dict, Any
import logging

from app.services.store_items import get_store_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/store",
    tags=["店家商品"],
)


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
