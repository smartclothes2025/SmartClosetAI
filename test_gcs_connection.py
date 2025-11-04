#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""測試 GCS 連接和權限"""

import os
from dotenv import load_dotenv
from google.cloud import storage

# 載入環境變數
load_dotenv()

print("=" * 60)
print("Google Cloud Storage 連接測試")
print("=" * 60)

# 1. 檢查環境變數
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
bucket_name = os.getenv("GCS_BUCKET_NAME")

print(f"\n[1] 環境變數檢查")
print(f"  GOOGLE_APPLICATION_CREDENTIALS: {credentials_path}")
print(f"  GCS_BUCKET_NAME: {bucket_name}")

if not credentials_path:
    print("  [ERROR] 缺少 GOOGLE_APPLICATION_CREDENTIALS")
    exit(1)

if not os.path.exists(credentials_path):
    print(f"  [ERROR] 憑證檔案不存在: {credentials_path}")
    exit(1)

print(f"  [OK] 憑證檔案存在")

# 2. 測試 Client 初始化
print(f"\n[2] 初始化 GCS Client")
try:
    client = storage.Client()
    print(f"  [OK] Client 初始化成功")
    print(f"  Project ID: {client.project}")
except Exception as e:
    print(f"  [ERROR] Client 初始化失敗: {e}")
    exit(1)

# 3. 測試 Bucket 存取
print(f"\n[3] 測試 Bucket 存取: {bucket_name}")
try:
    bucket = client.bucket(bucket_name)
    print(f"  [OK] Bucket 物件創建成功")
    
    # 嘗試檢查 bucket 是否存在
    exists = bucket.exists()
    print(f"  Bucket 存在: {exists}")
    
    if not exists:
        print(f"  [WARNING] Bucket '{bucket_name}' 不存在或無權限存取")
        print(f"  可能需要：")
        print(f"    1. 創建 Bucket")
        print(f"    2. 添加 Storage Object Viewer 權限")
except Exception as e:
    print(f"  [ERROR] Bucket 存取失敗: {e}")
    print(f"\n  原因可能是：")
    print(f"    - 服務帳號沒有 'storage.buckets.get' 權限")
    print(f"    - Bucket 不存在")

# 4. 測試上傳權限
print(f"\n[4] 測試上傳權限")
try:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob("test/connection_test.txt")
    
    test_content = "GCS connection test"
    blob.upload_from_string(test_content, content_type="text/plain")
    print(f"  [OK] 上傳測試成功")
    
    # 清理測試檔案
    blob.delete()
    print(f"  [OK] 刪除測試檔案成功")
    
except Exception as e:
    print(f"  [ERROR] 上傳測試失敗: {e}")
    print(f"\n  需要的權限：")
    print(f"    - storage.objects.create (上傳)")
    print(f"    - storage.objects.delete (刪除)")
    print(f"\n  建議角色：")
    print(f"    - Storage Object Admin (完整權限)")
    print(f"    - Storage Object Creator (僅上傳)")

# 5. 總結
print("\n" + "=" * 60)
print("測試完成")
print("=" * 60)
print("\n如果看到上傳失敗，請前往 Google Cloud Console:")
print("https://console.cloud.google.com/iam-admin/iam?project=smartclothes-287af")
print("\n給服務帳號添加以下角色：")
print("  - Storage Object Admin")
print("=" * 60)
