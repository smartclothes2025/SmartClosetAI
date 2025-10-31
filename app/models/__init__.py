#modles/__init__.py
from sqlalchemy.ext.declarative import declarative_base
from app.core.db import Base
from .auth import User
from app.models.wardrobe import WardrobeItem
from .outfit import Outfit
from .notification import Notification
