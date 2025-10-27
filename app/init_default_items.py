from core.db import SessionLocal
from models.wardrobe import WardrobeItem
from datetime import datetime, timezone

default_items = [
    {"category": "上衣", "name": "黑T", "cover_image_url": "/uploads/上衣/上衣1.jpg"},
    {"category": "上衣", "name": "粉泡泡袖上衣", "cover_image_url": "/uploads/上衣/上衣2.jpg"},
    {"category": "裙子", "name": "白色百褶裙", "cover_image_url": "/uploads/裙子/裙子1.jpg"},
    {"category": "裙子", "name": "卡其色長裙", "cover_image_url": "/uploads/裙子/裙子2.jpg"},
    {"category": "褲子", "name": "牛仔長褲", "cover_image_url": "/uploads/褲子/褲子1.jpg"},
    {"category": "褲子", "name": "牛仔短褲", "cover_image_url": "/uploads/褲子/褲子2.jpg"},
    {"category": "帽子", "name": "灰帽", "cover_image_url": "/uploads/帽子/帽子1.jpg"},
    {"category": "帽子", "name": "紅帽", "cover_image_url": "/uploads/帽子/帽子2.jpg"},
    {"category": "包包", "name": "咖啡色大包包", "cover_image_url": "/uploads/包包/包包1.jpg"},
    {"category": "包包", "name": "白色小包包", "cover_image_url": "/uploads/包包/包包2.jpg"}
]

def init_default_items():
    db = SessionLocal()
    try:
        for item in default_items:
            db_item = WardrobeItem(
                category=item["category"],  # 直接用中文字串
                name=item["name"],
                cover_image_url=item["cover_image_url"],
                attributes={},
                tags=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(db_item)
        db.commit()
        print("✅ 預設衣物已成功插入!")
    except Exception as e:
        db.rollback()
        print("❌ 發生錯誤:", e)
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    init_default_items()