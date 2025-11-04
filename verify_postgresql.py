#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""驗證 PostgreSQL 資料庫中的 GCS 上傳記錄"""

from dotenv import load_dotenv
import os

load_dotenv()

try:
    import psycopg2
except ImportError:
    print("[錯誤] 請安裝 psycopg2: pip install psycopg2-binary")
    exit(1)

print("=" * 60)
print("驗證 PostgreSQL 資料庫中的 GCS 上傳")
print("=" * 60)

# 連接資料庫
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "cguim")
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = os.getenv("PGPORT", "5432")
PGDATABASE = os.getenv("PGDATABASE", "closet")

print(f"\n連接資訊:")
print(f"  主機: {PGHOST}:{PGPORT}")
print(f"  資料庫: {PGDATABASE}")
print(f"  使用者: {PGUSER}")

try:
    conn = psycopg2.connect(
        host=PGHOST,
        port=PGPORT,
        database=PGDATABASE,
        user=PGUSER,
        password=PGPASSWORD
    )
    cursor = conn.cursor()
    print(f"  [成功] 資料庫連接成功")
except Exception as e:
    print(f"  [錯誤] 資料庫連接失敗: {e}")
    exit(1)

# 檢查 wardrobe_items 表
try:
    cursor.execute("SELECT COUNT(*) FROM wardrobe_items")
    total = cursor.fetchone()[0]
    print(f"\n總記錄數: {total}")
except Exception as e:
    print(f"\n[錯誤] 查詢失敗: {e}")
    conn.close()
    exit(1)

# 統計儲存位置
cursor.execute("SELECT cover_image_url FROM wardrobe_items WHERE cover_image_url IS NOT NULL")
all_urls = [r[0] for r in cursor.fetchall()]

gcs_count = sum(1 for url in all_urls if url.startswith('gs://'))
local_count = sum(1 for url in all_urls if url.startswith('/uploads/') or url.startswith('uploads/'))

print(f"\n儲存統計:")
print(f"  - GCS 雲端: {gcs_count} 筆 ({'%.1f' % (gcs_count/total*100 if total else 0)}%)")
print(f"  - 本地儲存: {local_count} 筆 ({'%.1f' % (local_count/total*100 if total else 0)}%)")

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
    if url:
        print(f"路徑: {url[:80]}..." if len(url) > 80 else f"路徑: {url}")
    print(f"時間: {created_at}")

conn.close()

print("\n" + "=" * 60)
if gcs_count > 0:
    print("✅ 結論: GCS 上傳已成功運作！")
    print(f"   已有 {gcs_count} 筆衣物儲存在 Google Cloud Storage")
else:
    print("⚠️  結論: 尚未有衣物上傳到 GCS")
    print("   請檢查後端配置和權限設定")
print("=" * 60)
