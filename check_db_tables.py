#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""檢查資料庫表結構"""

import sqlite3
import os

db_path = "wardrobe.db"

print("=" * 60)
print("檢查資料庫結構")
print("=" * 60)

if not os.path.exists(db_path):
    print(f"\n[錯誤] 找不到資料庫檔案: {db_path}")
    print("\n可能原因：")
    print("  1. 後端尚未啟動過")
    print("  2. 資料庫檔案在其他位置")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 列出所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print(f"\n資料庫檔案: {db_path}")
print(f"資料庫大小: {os.path.getsize(db_path)} bytes")
print(f"\n找到 {len(tables)} 個表：")

if not tables:
    print("  (無表)")
    print("\n資料庫可能尚未初始化。")
    print("請啟動後端，讓資料庫自動建立。")
else:
    for table in tables:
        table_name = table[0]
        print(f"\n表名: {table_name}")
        
        # 顯示表結構
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        print("  欄位:")
        for col in columns:
            col_id, col_name, col_type, not_null, default, pk = col
            print(f"    - {col_name} ({col_type})")
        
        # 顯示記錄數
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"  記錄數: {count}")

conn.close()

print("\n" + "=" * 60)
