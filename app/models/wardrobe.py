from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.core.db import Base
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from enum import Enum
from pathlib import Path

class CategoryEnum(str, Enum):
    TOP = "tops"
    SKIRT = "skirts"
    PANTS = "pants"
    DRESS = "dresses"
    OUTER = "outerwear"
    SHOES = "shoes"
    HAT = "hats"
    BAG = "bags"
    ACCESSORY = "accessories"
    BOTTOMS = "bottoms"
    SPECIAL = "special"
    JEWELRY = "jewelry"
    PANTSUITS = "pantsuits"
    SOCKS = "socks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=True)
    category = Column(
        SQLEnum(CategoryEnum, name="category_enum", create_constraint=False, values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    name = Column(String, nullable=True)
    cover_image_url = Column(String, nullable=True)
    color = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    style = Column(String, nullable=True)
    attributes = Column(JSONB, nullable=True, default=dict)
    tags = Column(ARRAY(String), nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="wardrobe")
    # 與 Outfit 的多對多關係
    in_outfits = relationship("Outfit", secondary="outfit_items", back_populates="items")


# 與現有資料庫中 'wardrobe' 表對應的簡化模型（依你提供的欄位）
class Wardrobe(Base):
    __tablename__ = "wardrobe"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    filename = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    style = Column(String, nullable=True)
    occasion = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=True)

    def save_item_to_wardrobe(self, db, current_user, final_path, resolved_category, resolved_color, resolved_style, resolved_occasion, name: str = None):
            # final_path 可能是 str 或 Path，統一轉 Path
            p = Path(final_path)

            # 轉換 category（若是字串就嘗試轉 enum）
            cat_val = None
            try:
                if isinstance(resolved_category, CategoryEnum):
                    cat_val = resolved_category
                elif isinstance(resolved_category, str) and resolved_category in [e.value for e in CategoryEnum]:
                    cat_val = CategoryEnum(resolved_category)
            except Exception:
                cat_val = None

            # attributes 儲存額外資訊（包含場合）
            attrs = {}
            if resolved_occasion:
                attrs["occasion"] = resolved_occasion

            # 使用傳入的 name（優先），否則使用檔名的 stem（不含副檔名）
            display_name = (name or "").strip() or (p.stem if p.name else None)

            item = WardrobeItem(
                user_id=current_user.id,
                name=display_name,
                category=cat_val,
                color=resolved_color,
                style=resolved_style,
                cover_image_url=str(p.as_posix()),
                attributes=attrs
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return item