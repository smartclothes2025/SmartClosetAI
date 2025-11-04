#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查看 GCS 上傳記錄"""

import psycopg2

print("=" * 60)
print("查看 GCS 上傳記錄")
print("=" * 60)

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='closet',
        user='postgres',
        password='cguim'
    )
    cursor = conn.cursor()
    
    # 查看 GCS 記錄
    cursor.execute("""
        SELECT name, cover_image_url, created_at 
        FROM wardrobe_items 
        WHERE cover_image_url LIKE 'gs://%'
        ORDER BY created_at DESC
    """)
    
    gcs_records = cursor.fetchall()
    
    print(f"\n找到 {len(gcs_records)} 筆 GCS 記錄:\n")
    
    if gcs_records:
        for name, url, created_at in gcs_records:
            print(f"  - {name}")
            print(f"    路徑: {url}")
            print(f"    時間: {created_at}")
            print()
    else:
        print("  (無 GCS 記錄)")
    
    # 查看最近的本地記錄
    print("\n最近 3 筆本地儲存:")
    cursor.execute("""
        SELECT name, cover_image_url, created_at 
        FROM wardrobe_items 
        WHERE cover_image_url LIKE '/uploads/%' OR cover_image_url LIKE 'uploads/%'
        ORDER BY created_at DESC
        LIMIT 3
    """)
    
    local_records = cursor.fetchall()
    for name, url, created_at in local_records:
        print(f"\n  - {name}")
        print(f"    路徑: {url}")
        print(f"    時間: {created_at}")
    
    conn.close()
    
except Exception as e:
    print(f"\n錯誤: {e}")

print("\n" + "=" * 60)
