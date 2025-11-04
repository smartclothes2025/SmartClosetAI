#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""檢查最近的上傳記錄"""

import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("檢查最近的上傳記錄")
print("=" * 60)

# 連接資料庫
db_path = "wardrobe.db"
if not os.path.exists(db_path):
    print(f"\n[錯誤] 找不到資料庫: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查詢最近 5 筆上傳
print("\n最近 5 筆上傳記錄：")
print("-" * 60)

query = """
SELECT 
    id, 
    filename, 
    category,
    color,
    style,
    brand
FROM wardrobe 
ORDER BY id DESC 
LIMIT 5
"""

cursor.execute(query)
rows = cursor.fetchall()

if not rows:
    print("  (無記錄)")
    print("\n[提示] 資料庫中還沒有任何上傳記錄。")
    print("      可能原因：")
    print("      1. 後端尚未啟動")
    print("      2. 還沒有成功上傳過衣物")
    print("      3. 上傳過程中發生錯誤")
else:
    for row in rows:
        item_id, filename, category, color, style, brand = row
        
        # 判斷儲存位置
        if filename and filename.startswith("gs://"):
            storage_type = "[GCS 雲端]"
        elif filename and filename.startswith("/uploads/"):
            storage_type = "[本地儲存]"
        elif filename and filename.startswith("uploads/"):
            storage_type = "[本地儲存]"
        else:
            storage_type = "[未知]"
        
        print(f"\nID: {item_id}")
        print(f"檔名: {filename}")
        print(f"類別: {category}")
        print(f"顏色: {color}")
        print(f"風格: {style}")
        print(f"品牌: {brand}")
        print(f"儲存: {storage_type}")

conn.close()

print("\n" + "=" * 60)
print("判斷方式：")
print("  - 檔名以 gs:// 開頭 = 已上傳到 GCS 雲端")
print("  - 檔名以 /uploads/ 開頭 = 儲存在本地")
print("\n如何上傳：")
print("  1. 確保後端正在運行")
print("  2. 前端重新整理後上傳圖片")
print("  3. 查看後端終端的上傳日誌")
print("=" * 60)
