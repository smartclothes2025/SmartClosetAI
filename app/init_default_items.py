from core.db import SessionLocal
from models.wardrobe import WardrobeItem
from datetime import datetime, timezone

default_items = [
    {"category": "tops", "name": "Black T-shirt", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "tops", "name": "Pink Puff Sleeve Top", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "skirts", "name": "White Pleated Skirt", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "skirts", "name": "Khaki Long Skirt", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "pants", "name": "Blue Jeans", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "pants", "name": "Denim Shorts", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "hats", "name": "Gray Hat", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "hats", "name": "Red Hat", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "bags", "name": "Brown Large Bag", "cover_image_url": "/uploads/bags/bag_1.jpg"},
    {"category": "bags", "name": "White Small Bag", "cover_image_url": "/uploads/bags/bag_1.jpg"}
]

def init_default_items():
    db = SessionLocal()
    try:
        for item in default_items:
            db_item = WardrobeItem(
                category=item["category"],
                name=item["name"],
                cover_image_url=item["cover_image_url"],
                attributes={},
                tags=[],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(db_item)
        db.commit()
        print("✅ Default wardrobe items have been successfully inserted!")
    except Exception as e:
        db.rollback()
        print("❌ An error occurred:", e)
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    init_default_items()