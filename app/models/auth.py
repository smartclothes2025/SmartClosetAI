#models/auth.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.core.db import Base
from datetime import datetime, timezone

class User(Base):
    __tablename__ = "app_users"

    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String)
    # 使用者自介（資料庫欄位名依需求：interformation）
    interformation = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    firebase_uid = Column(String, nullable=True) 
    role = Column(String)
    picture = Column(String, nullable=True)  # 使用者頭貼 GCS URI 
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # 用户的衣物
    wardrobe = relationship("WardrobeItem", back_populates="user")
    
    # 用户的穿搭记录
    outfits = relationship("Outfit", back_populates="user")
    
    # 用户的通知
    notifications = relationship("Notification", back_populates="user")
    
    # 用户的推薦記錄
    recommendations = relationship("Recommendation", back_populates="user")