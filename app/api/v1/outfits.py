# app/api/v1/outfits.py
"""
Outfit API - 穿搭管理
支援兩階段保存流程：
1. 第一階段：保存圖片和基本資訊
2. 第二階段：補充標題、標籤、分享內容等詳細資訊
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, and_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import logging
from uuid import UUID

from app.core.db import get_db
from app.models.outfit import Outfit
from app.models.wardrobe import WardrobeItem
from app.models.auth import User

logger = logging.getLogger(__name__)

router = APIRouter()

# ===== Pydantic Models =====

class OutfitCreateStage1(BaseModel):
    """第一階段：保存圖片"""
    # 支援多種格式，例如：
    # - YYYY-MM-DD
    # - YYYY-MM-DD HH:MM
    # - 2025-11-26T14:30:00（ISO 格式）
    worn_date: str
    image_url: str  # 圖片 URL 或 base64
    item_ids: Optional[List[int]] = []  # 使用的衣物 ID 列表

class OutfitUpdateStage2(BaseModel):
    """第二階段：補充詳細資訊"""
    name: Optional[str] = None  # 標題
    description: Optional[str] = None  # 想要分享什麼
    tags: Optional[str] = None  # 標籤（逗號分隔）

class OutfitResponse(BaseModel):
    id: int
    name: Optional[str]
    worn_date: str
    image_url: Optional[str]
    description: Optional[str]
    tags: Optional[str]
    created_at: datetime
    user_id: UUID
    item_count: int = 0

    class Config:
        from_attributes = True

# ===== Helper Functions =====

def get_current_user_from_header(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """從 Header 獲取當前用戶"""
    from app.api.v1.auth import AUTH_BEARER_PREFIX, ERR_INVALID_TOKEN, ERR_USER_NOT_FOUND
    import uuid as _uuid
    
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    if auth_header.startswith(AUTH_BEARER_PREFIX):
        token = auth_header.split(" ", 1)[1]
    
    if not token:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    try:
        _uuid.UUID(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)
    return user

# ===== API Endpoints =====

@router.post("/outfits", response_model=OutfitResponse)
async def create_outfit_stage1(
    outfit_data: OutfitCreateStage1,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    第一階段：創建穿搭並保存圖片
    - 保存穿搭圖片（AI 生成或上傳）
    - 關聯使用的衣物
    - 設定穿著日期
    """
    try:
        # 解析日期與時間（支援多種格式），若只提供日期則時間設為 00:00
        def _parse_worn_date(s: str) -> datetime:
            if not s or not isinstance(s, str):
                raise ValueError("worn_date 必須為字串，格式例如 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM'")
            v = s.strip()
            # 先嘗試 ISO 格式
            try:
                return datetime.fromisoformat(v)
            except Exception:
                pass

            # 嘗試常見格式
            fmts = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
            for f in fmts:
                try:
                    return datetime.strptime(v, f)
                except Exception:
                    continue
            raise ValueError("無法解析的日期格式，請使用 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM' 或 ISO 字串")

        worn_date_obj = _parse_worn_date(outfit_data.worn_date)
        
        # 檢查該日期是否已有穿搭
        existing = db.query(Outfit).filter(
            and_(
                Outfit.user_id == current_user.id,
                Outfit.worn_date == worn_date_obj
            )
        ).first()
        
        if existing:
            # 更新現有穿搭的圖片
            if outfit_data.image_url:
                existing.image_url = outfit_data.image_url
            outfit = existing
            logger.info(f"更新現有穿搭 ID={outfit.id}")
        else:
            # 創建新穿搭
            outfit = Outfit(
                user_id=current_user.id,
                worn_date=worn_date_obj,
                image_url=outfit_data.image_url,
            )
            db.add(outfit)
            logger.info(f"創建新穿搭，日期={outfit_data.worn_date}")
        
        # 關聯衣物
        if outfit_data.item_ids:
            items = db.query(WardrobeItem).filter(
                and_(
                    WardrobeItem.id.in_(outfit_data.item_ids),
                    WardrobeItem.user_id == current_user.id
                )
            ).all()
            outfit.items = items
            logger.info(f"關聯 {len(items)} 件衣物")
        
        db.commit()
        db.refresh(outfit)
        
        return OutfitResponse(
            id=outfit.id,
            name=outfit.name,
            worn_date=outfit.worn_date.strftime("%Y-%m-%d %H:%M"),
            image_url=outfit.image_url,
            description=outfit.description,
            tags=outfit.tags,
            created_at=outfit.created_at,
            user_id=outfit.user_id,
            item_count=len(outfit.items)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"日期格式錯誤: {str(e)}")
    except Exception as e:
        db.rollback()
        logger.error(f"創建穿搭失敗: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"創建穿搭失敗: {str(e)}")

@router.patch("/outfits/{outfit_id}", response_model=OutfitResponse)
async def update_outfit_stage2(
    outfit_id: int,
    outfit_data: OutfitUpdateStage2,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    第二階段：補充穿搭詳細資訊
    - 標題
    - 想要分享什麼
    - 標籤
    - 私人筆記
    - 是否公開
    """
    try:
        outfit = db.query(Outfit).filter(
            and_(
                Outfit.id == outfit_id,
                Outfit.user_id == current_user.id
            )
        ).first()
        
        if not outfit:
            raise HTTPException(status_code=404, detail="穿搭不存在")
        
        # 更新欄位
        if outfit_data.name is not None:
            outfit.name = outfit_data.name
        if outfit_data.description is not None:
            outfit.description = outfit_data.description
        if outfit_data.tags is not None:
            outfit.tags = outfit_data.tags
        
        db.commit()
        db.refresh(outfit)
        
        logger.info(f"更新穿搭 ID={outfit_id} 詳細資訊")
        
        return OutfitResponse(
            id=outfit.id,
            name=outfit.name,
            worn_date=outfit.worn_date.strftime("%Y-%m-%d %H:%M"),
            image_url=outfit.image_url,
            description=outfit.description,
            tags=outfit.tags,
            created_at=outfit.created_at,
            user_id=outfit.user_id,
            item_count=len(outfit.items)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新穿搭失敗: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新穿搭失敗: {str(e)}")



@router.put("/outfits/{outfit_id}", response_model=OutfitResponse)
async def replace_outfit(
    outfit_id: int,
    outfit_data: OutfitUpdateStage2,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db),
):
    """兼容 PUT 方法，等同於 PATCH /outfits/{outfit_id} 的行為，由現有函式處理更新邏輯。"""
    # delegate to existing implementation to avoid duplicating logic
    return await update_outfit_stage2(outfit_id=outfit_id, outfit_data=outfit_data, current_user=current_user, db=db)

@router.get("/outfits", response_model=List[OutfitResponse])
async def list_outfits(
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    查詢用戶的穿搭列表
    - 可按年月篩選
    - 返回穿搭圖片和基本資訊
    """
    try:
        query = db.query(Outfit).filter(Outfit.user_id == current_user.id)
        
        # 按年月篩選
        if year and month:
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)
            
            query = query.filter(
                and_(
                    Outfit.worn_date >= start_date,
                    Outfit.worn_date < end_date
                )
            )
        
        outfits = query.order_by(Outfit.worn_date.desc()).limit(limit).all()
        
        return [
            OutfitResponse(
                id=outfit.id,
                name=outfit.name,
                worn_date=outfit.worn_date.strftime("%Y-%m-%d %H:%M"),
                image_url=outfit.image_url,
                description=outfit.description,
                tags=outfit.tags,
                created_at=outfit.created_at,
                user_id=outfit.user_id,
                item_count=len(outfit.items)
            )
            for outfit in outfits
        ]
        
    except Exception as e:
        logger.error(f"查詢穿搭列表失敗: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")

@router.get("/outfits/{outfit_id}", response_model=OutfitResponse)
async def get_outfit(
    outfit_id: int,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    獲取單個穿搭的詳細資訊
    """
    outfit = db.query(Outfit).filter(
        and_(
            Outfit.id == outfit_id,
            Outfit.user_id == current_user.id
        )
    ).first()
    
    if not outfit:
        raise HTTPException(status_code=404, detail="穿搭不存在")
    
    return OutfitResponse(
        id=outfit.id,
        name=outfit.name,
        worn_date=outfit.worn_date.strftime("%Y-%m-%d %H:%M"),
        image_url=outfit.image_url,
        description=outfit.description,
        tags=outfit.tags,
        created_at=outfit.created_at,
        user_id=outfit.user_id,
        item_count=len(outfit.items)
    )

@router.delete("/outfits/{outfit_id}")
async def delete_outfit(
    outfit_id: int,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    刪除穿搭
    """
    outfit = db.query(Outfit).filter(
        and_(
            Outfit.id == outfit_id,
            Outfit.user_id == current_user.id
        )
    ).first()
    
    if not outfit:
        raise HTTPException(status_code=404, detail="穿搭不存在")
    
    db.delete(outfit)
    db.commit()
    
    logger.info(f"刪除穿搭 ID={outfit_id}")
    
    return {"success": True, "message": "穿搭已刪除"}
