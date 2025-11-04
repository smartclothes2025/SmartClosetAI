#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接測試 GCS 上傳函數"""

import os
from dotenv import load_dotenv
from app.services.storage import upload_file_to_gcs

load_dotenv()

print("=" * 60)
print("測試 GCS 上傳函數")
print("=" * 60)

bucket_name = os.getenv("GCS_BUCKET_NAME")
print(f"\nBucket: {bucket_name}")

# 創建測試檔案
test_content = b"Test upload from Python"
test_path = "test/upload_test.txt"

print(f"目標路徑: {test_path}")
print("\n嘗試上傳...")

try:
    result = upload_file_to_gcs(
        file_bytes=test_content,
        destination_blob_name=test_path,
        mime_type="text/plain",
        bucket_name=bucket_name,
        public=False
    )
    print(f"\n[成功] 上傳成功!")
    print(f"GCS URI: {result}")
except Exception as e:
    print(f"\n[錯誤] 上傳失敗!")
    print(f"錯誤類型: {type(e).__name__}")
    print(f"錯誤訊息: {e}")
    
    import traceback
    print("\n完整錯誤:")
    traceback.print_exc()

print("\n" + "=" * 60)
