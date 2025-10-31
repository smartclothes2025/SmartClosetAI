# app/models/notification.py
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
from app.core.db import Base
import uuid

class Notification(Base):
    """通知模型"""
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    
    # 通知類型：new_item, suggestion, alert, system
    type = Column(String, nullable=False, default="new_item")
    
    # 通知訊息
    message = Column(Text, nullable=False)
    
    # 詳細資訊（可選）
    details = Column(Text, nullable=True)
    
    # 額外資料（JSON 格式）
    payload = Column(JSONB, nullable=True)
    
    # 是否已讀
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    
    # 時間戳記
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    # 關聯
    user = relationship("User", back_populates="notifications")
    
    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type}, is_read={self.is_read})>"
