#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""檢查上傳流程的環境變數"""

import os
import sys

# 添加專案路徑
sys.path.insert(0, r'C:\Users\Administrator\Desktop\SmartClosetAI')

print("=" * 60)
print("檢查上傳流程環境變數")
print("=" * 60)

# 模擬 clothes.py 載入過程
print("\n[步驟 1] 載入前")
print(f"USE_GCS = {os.getenv('USE_GCS')}")
print(f"GCS_BUCKET_NAME = {os.getenv('GCS_BUCKET_NAME')}")

print("\n[步驟 2] 執行 load_dotenv()")
from dotenv import load_dotenv
load_dotenv()

print("\n[步驟 3] 載入後")
USE_GCS_raw = os.getenv("USE_GCS", "false")
print(f"USE_GCS (原始) = '{USE_GCS_raw}'")
print(f"USE_GCS (小寫) = '{USE_GCS_raw.lower()}'")
print(f"USE_GCS (比較) = {USE_GCS_raw.lower() == 'true'}")

USE_GCS = USE_GCS_raw.lower() == "true"
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

print(f"\nUSE_GCS = {USE_GCS}")
print(f"GCS_BUCKET_NAME = '{GCS_BUCKET_NAME}'")

print("\n[步驟 4] 條件判斷")
print(f"if USE_GCS and GCS_BUCKET_NAME:")
print(f"  USE_GCS = {USE_GCS} (type: {type(USE_GCS)})")
print(f"  GCS_BUCKET_NAME = '{GCS_BUCKET_NAME}' (type: {type(GCS_BUCKET_NAME)})")
print(f"  bool(GCS_BUCKET_NAME) = {bool(GCS_BUCKET_NAME)}")
print(f"  條件結果 = {USE_GCS and GCS_BUCKET_NAME}")

if USE_GCS and GCS_BUCKET_NAME:
    print("\n  [結果] 會嘗試上傳到 GCS")
else:
    print("\n  [結果] 會使用本地儲存")
    
print("\n[步驟 5] 測試 GCS 上傳函數")
try:
    from app.services.storage import upload_file_to_gcs
    print("  upload_file_to_gcs 函數匯入成功")
    
    # 測試上傳
    test_bytes = b"test"
    result = upload_file_to_gcs(
        file_bytes=test_bytes,
        destination_blob_name="test/flow_test.txt",
        mime_type="text/plain",
        bucket_name=GCS_BUCKET_NAME,
        public=False
    )
    print(f"  測試上傳成功: {result}")
except Exception as e:
    print(f"  測試上傳失敗: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
