#models/outfit.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base

# 关联表：记录穿搭和衣物的多对多关系
outfit_items = Table(
    'outfit_items',
    Base.metadata,
    Column('outfit_id', Integer, ForeignKey('outfits.id'), primary_key=True),
    Column('item_id', Integer, ForeignKey('wardrobe_items.id'), primary_key=True)
)

class Outfit(Base):
    __tablename__ = "outfits"

    id = Column(Integer, primary_key=True, index=True)
    
    # 基本資訊
    name = Column(String, index=True, nullable=True)  # 穿搭標題
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    worn_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)  # 穿著日期
    
    # 圖片相關（第一階段）
    image_url = Column(String, nullable=True)  # 穿搭圖片 GCS URI 或 URL
    is_ai_generated = Column(Boolean, default=False)  # 是否為 AI 生成
    
    # 詳細資訊（第二階段）
    description = Column(Text, nullable=True)  # 想要分享什麼
    tags = Column(String, nullable=True)  # 標籤（逗號分隔）
    note = Column(Text, nullable=True)  # 私人筆記
    
    # 狀態
    is_complete = Column(Boolean, default=False)  # 是否完成兩階段填寫
    is_public = Column(Boolean, default=False)  # 是否公開分享
    
    # 與 WardrobeItem 的多對多關係
    items = relationship("WardrobeItem", secondary='outfit_items', back_populates="in_outfits")
    
    # 創建者（用戶）
    user_id = Column(Integer, ForeignKey('app_users.id'))
    user = relationship("User", back_populates="outfits")