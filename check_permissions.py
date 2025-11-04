#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""檢查服務帳號權限"""

import os
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account

load_dotenv()

print("=" * 60)
print("檢查 GCS 服務帳號權限")
print("=" * 60)

credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
bucket_name = os.getenv("GCS_BUCKET_NAME")

if not credentials_path or not os.path.exists(credentials_path):
    print("[ERROR] 憑證檔案不存在")
    exit(1)

# 讀取服務帳號資訊
credentials = service_account.Credentials.from_service_account_file(credentials_path)
client = storage.Client(credentials=credentials)

print(f"\n服務帳號: {credentials.service_account_email}")
print(f"專案 ID: {credentials.project_id}")
print(f"Bucket: {bucket_name}")

# 測試權限
print("\n" + "=" * 60)
print("測試權限")
print("=" * 60)

bucket = client.bucket(bucket_name)

# 1. 測試 storage.buckets.get
print("\n[1] storage.buckets.get (檢查 bucket 是否存在)")
try:
    exists = bucket.exists()
    if exists:
        print(f"  [OK] 有權限 - Bucket 存在")
    else:
        print(f"  [WARNING] Bucket 不存在")
except Exception as e:
    print(f"  [ERROR] 沒有權限: {e}")

# 2. 測試 storage.objects.create
print("\n[2] storage.objects.create (上傳檔案)")
try:
    blob = bucket.blob("test/permission_test.txt")
    blob.upload_from_string("test", content_type="text/plain")
    print(f"  [OK] 有權限 - 上傳成功")
    
    # 3. 測試 storage.objects.delete
    print("\n[3] storage.objects.delete (刪除檔案)")
    try:
        blob.delete()
        print(f"  [OK] 有權限 - 刪除成功")
    except Exception as e:
        print(f"  [ERROR] 沒有權限: {e}")
        
except Exception as e:
    print(f"  [ERROR] 沒有權限: {e}")

# 4. 測試 storage.objects.list
print("\n[4] storage.objects.list (列出檔案)")
try:
    blobs = list(bucket.list_blobs(max_results=1))
    print(f"  [OK] 有權限 - 找到 {len(blobs)} 個檔案")
except Exception as e:
    print(f"  [ERROR] 沒有權限: {e}")

# 總結
print("\n" + "=" * 60)
print("權限檢查總結")
print("=" * 60)
print("\n建議的角色：")
print("  - Storage Object Admin (包含所有權限)")
print("\n添加步驟：")
print("  1. 前往 https://console.cloud.google.com/iam-admin/iam?project=smartclothes-287af")
print("  2. 找到服務帳號並點擊編輯 (鉛筆圖示)")
print("  3. 點擊「新增其他角色」")
print("  4. 搜尋並選擇「Storage Object Admin」")
print("  5. 點擊「儲存」")
print("=" * 60)
