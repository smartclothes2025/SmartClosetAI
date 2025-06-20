#core/init_db.py
from app.core.db import Base, engine
from app.models.wardrobe import Wardrobe
from app.models.auth import User
from app.models.outfit import Outfit

def init_db():
    Base.metadata.create_all(bind=engine)
    print("資料庫建立完成")

if __name__ == "__main__":
    init_db()