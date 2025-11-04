#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""初始化資料庫，創建缺少的表"""

from app.core.db import Base, engine
from app.models.wardrobe import WardrobeItem, Wardrobe
from app.models.auth import User
from app.models.outfit import Outfit
from app.models.posts import Post
import sqlite3

print("=" * 60)
print("初始化資料庫")
print("=" * 60)

# 檢查現有表
print("\n[步驟 1] 檢查現有表...")
conn = sqlite3.connect("wardrobe.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
existing_tables = [row[0] for row in cursor.fetchall()]
print(f"現有表: {existing_tables}")
conn.close()

# 創建所有表
print("\n[步驟 2] 創建缺少的表...")
try:
    Base.metadata.create_all(bind=engine)
    print("[成功] 資料庫表已更新")
except Exception as e:
    print(f"[錯誤] 創建表失敗: {e}")
    exit(1)

# 再次檢查
print("\n[步驟 3] 驗證表結構...")
conn = sqlite3.connect("wardrobe.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
all_tables = [row[0] for row in cursor.fetchall()]
print(f"更新後的表: {all_tables}")

# 檢查 wardrobe_items 表
if 'wardrobe_items' in all_tables:
    print("\n[成功] wardrobe_items 表已創建！")
    cursor.execute("PRAGMA table_info(wardrobe_items);")
    columns = cursor.fetchall()
    print("  欄位:")
    for col in columns:
        col_id, col_name, col_type, not_null, default, pk = col
        print(f"    - {col_name} ({col_type})")
else:
    print("\n[警告] wardrobe_items 表尚未創建")

conn.close()

print("\n" + "=" * 60)
print("資料庫初始化完成！")
print("=" * 60)
print("\n下一步：")
print("  1. 重新啟動後端: python start_server.py")
print("  2. 前端重新整理並上傳圖片")
print("  3. 執行 python check_last_upload.py 確認")
print("=" * 60)
