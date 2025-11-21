# app/models/outfit.py

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Table,
    DateTime,
    Text,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.db import Base  # ✅ 一定要有這行，Base 才會存在


# 多對多關聯表：Outfit <-> WardrobeItem
outfit_items = Table(
    "outfit_items",
    Base.metadata,
    Column("outfit_id", Integer, ForeignKey("outfits.id"), primary_key=True),
    Column("item_id", Integer, ForeignKey("wardrobe_items.id"), primary_key=True),
)


class Outfit(Base):
    __tablename__ = "outfits"

    id = Column(Integer, primary_key=True, index=True)

    # 基本資訊
    name = Column(String, index=True, nullable=True)  # 穿搭標題
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    worn_date = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )  # 穿著日期

    # 圖片相關
    image_url = Column(String, nullable=True)  # GCS URI 或 URL

    # 詳細資訊
    description = Column(Text, nullable=True)  # 想分享的內容
    tags = Column(String, nullable=True)  # 標籤（逗號分隔）
    visibility = Column(Text, nullable=True)  # ✅ 對應你 DB 新增的 visibility 欄位

    # 狀態
    # is_complete = Column(Boolean, default=False)  # 是否完成填寫
    # is_public = Column(Boolean, default=False)  # 是否公開分享

    # 與 WardrobeItem 的多對多關係
    items = relationship(
        "WardrobeItem",
        secondary="outfit_items",
        back_populates="in_outfits",
    )

    # 建立者（使用者）
    user_id = Column(Integer, ForeignKey("app_users.id"))
    user = relationship("User", back_populates="outfits")
