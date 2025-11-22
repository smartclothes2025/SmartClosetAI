# app/models/recommendation.py

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.db import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False, index=True)
    kind = Column(String, nullable=False, index=True)  # 'daily_inactive', 'ai_outfit', etc.
    payload = Column(JSONB, nullable=False)  # JSON payload containing recommendation data
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship to user
    user = relationship("User", back_populates="recommendations")


# Update User model to include recommendations relationship
# Note: This should be added to app/models/auth.py in the User class:
# recommendations = relationship("Recommendation", back_populates="user")
