import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load env vars
load_dotenv()

# Get database URL
db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/closet')
print(f'DB URL: {db_url}')

# Try to connect
try:
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Query wardrobe items
    from app.models.wardrobe import WardrobeItem
    items = session.query(WardrobeItem).limit(5).all()
    
    print(f'\nFound {len(items)} wardrobe items (showing first 5):')
    for item in items:
        print(f'  - ID: {item.id}')
        print(f'    Name: {item.name}')
        print(f'    Category: {item.category}')
        print(f'    Image URL: {item.cover_image_url}')
        print()
        
except Exception as e:
    print(f'Database query failed: {e}')
    import traceback
    traceback.print_exc()
