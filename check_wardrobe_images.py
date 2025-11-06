"""
檢查衣櫃中的圖片 URL 格式
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

# 連接資料庫
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

print("=" * 80)
print("檢查衣櫃圖片 URL")
print("=" * 80)

with engine.connect() as conn:
    # 查詢最近的衣物記錄
    result = conn.execute(text("""
        SELECT id, name, category, cover_image_url 
        FROM wardrobe_items 
        WHERE cover_image_url IS NOT NULL 
        ORDER BY created_at DESC 
        LIMIT 10
    """))
    
    items = result.fetchall()
    
    if not items:
        print("\n❌ 沒有找到任何有圖片的衣物記錄")
    else:
        print(f"\n找到 {len(items)} 筆記錄:\n")
        for idx, item in enumerate(items, 1):
            print(f"[{idx}] {item.name} ({item.category})")
            print(f"    ID: {item.id}")
            print(f"    URL: {item.cover_image_url}")
            
            # 測試 URL 是否可訪問
            if item.cover_image_url and item.cover_image_url.startswith('http'):
                import requests
                try:
                    resp = requests.head(item.cover_image_url, timeout=5)
                    if resp.status_code == 200:
                        print(f"    ✅ URL 可訪問")
                    else:
                        print(f"    ❌ HTTP {resp.status_code}")
                except Exception as e:
                    print(f"    ❌ 無法訪問: {e}")
            print()

print("=" * 80)
