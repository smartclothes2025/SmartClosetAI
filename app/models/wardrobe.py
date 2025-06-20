#models/wardrobe.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.db import Base

# app/models/wardrobe.py
class Wardrobe(Base):
    __tablename__ = "wardrobe"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    category = Column(String, nullable=False)
    color = Column(String)           # JSON string of color list
    style = Column(String)
    occasion = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="wardrobe")





