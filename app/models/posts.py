from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.db import Base
import uuid

class Post(Base):
    __tablename__ = "user_post"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False)

    # 文字內容
    type = Column(String, default="post")   # 預設 post
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    tag = Column(String, nullable=True)

    # 圖片與媒體 JSON 陣列 → [{type, gcs_uri, url, is_cover}]
    media = Column(JSONB, nullable=True)

    # 權限 public / friends / private
    visibility = Column(String, default="public")

    # 計數
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # 關聯，讓你可以做 post.user.display_name
    user = relationship("User", back_populates="posts")
