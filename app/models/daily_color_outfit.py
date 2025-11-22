# app/models/daily_color_outfit.py

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date
from sqlalchemy.dialects.postgresql import JSONB

from app.core.db import Base


class DailyColorOutfit(Base):
    """每日色系穿搭快取表"""
    __tablename__ = "daily_color_outfits"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)  # 日期 2025-11-21
    gender = Column(String, nullable=False, index=True)  # women / men
    color_family = Column(String, nullable=False, index=True)  # neutral / khaki / blue / pink / green
    is_main_color = Column(Boolean, default=False)  # 是否為今日主色
    outfits_json = Column(JSONB, nullable=False)  # 該色系的 3 套穿搭（JSON）
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
