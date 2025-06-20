#models/user.py
from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.db import Base

class Outfit(Base):
    __tablename__ = "outfits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)