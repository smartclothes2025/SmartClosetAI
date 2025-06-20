#modles/__init__.py
from sqlalchemy.ext.declarative import declarative_base
from app.core.db import Base
from .auth import User
from .wardrobe import Wardrobe
from .outfit import Outfit
