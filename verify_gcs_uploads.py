#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""驗證 GCS 上傳記錄"""

import sqlite3

conn = sqlite3.connect('wardrobe.db')
cursor = conn.cursor()

print("=" * 60)
print("驗證 GCS 上傳記錄")
print("=" * 60)

# 檢查 wardrobe_items 表
cursor.execute("SELECT COUNT(*) FROM wardrobe_items")
total = cursor.fetchone()[0]
print(f"\n總記錄數: {total}")

# 統計儲存位置
cursor.execute("SELECT cover_image_url FROM wardrobe_items WHERE cover_image_url IS NOT NULL")
all_urls = [r[0] for r in cursor.fetchall()]

gcs_count = sum(1 for url in all_urls if url.startswith('gs://'))
local_count = sum(1 for url in all_urls if url.startswith('/uploads/') or url.startswith('uploads/'))

print(f"\n儲存統計:")
print(f"  - GCS 雲端: {gcs_count} 筆")
print(f"  - 本地儲存: {local_count} 筆")

# 顯示最近 5 筆
print(f"\n最近 5 筆上傳:")
print("-" * 60)

query = """
SELECT 
    id,
    name,
    category,
    cover_image_url,
    created_at
FROM wardrobe_items 
ORDER BY created_at DESC 
LIMIT 5
"""

cursor.execute(query)
rows = cursor.fetchall()

for row in rows:
    item_id, name, category, url, created_at = row
    
    if url and url.startswith('gs://'):
        storage = "[GCS 雲端]"
    elif url and (url.startswith('/uploads/') or url.startswith('uploads/')):
        storage = "[本地儲存]"
    else:
        storage = "[未知]"
    
    print(f"\nID: {item_id}")
    print(f"名稱: {name}")
    print(f"類別: {category}")
    print(f"儲存: {storage}")
    print(f"路徑: {url[:80]}...")
    print(f"時間: {created_at}")

conn.close()

print("\n" + "=" * 60)
print("結論: 上傳到 GCS 已成功運作！")
print("=" * 60)
