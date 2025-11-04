#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""測試環境變數是否正確載入"""

import os
from dotenv import load_dotenv

print("=" * 60)
print("測試環境變數載入")
print("=" * 60)

# 1. 載入前
print("\n[載入前]")
print(f"USE_GCS = {os.getenv('USE_GCS')}")
print(f"GCS_BUCKET_NAME = {os.getenv('GCS_BUCKET_NAME')}")

# 2. 載入 .env
print("\n[執行 load_dotenv()]")
load_dotenv()

# 3. 載入後
print("\n[載入後]")
USE_GCS_raw = os.getenv("USE_GCS", "false")
USE_GCS = USE_GCS_raw.lower() == "true"
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")

print(f"USE_GCS (原始值) = '{USE_GCS_raw}'")
print(f"USE_GCS (布林值) = {USE_GCS}")
print(f"GCS_BUCKET_NAME = '{GCS_BUCKET_NAME}'")
print(f"GOOGLE_APPLICATION_CREDENTIALS = {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")

# 4. 檢查條件
print("\n[條件判斷]")
if USE_GCS and GCS_BUCKET_NAME:
    print("✓ 條件滿足：會嘗試上傳到 GCS")
else:
    print("✗ 條件不滿足：會使用本地儲存")
    if not USE_GCS:
        print("  原因：USE_GCS 為 False")
    if not GCS_BUCKET_NAME:
        print("  原因：GCS_BUCKET_NAME 為空")

print("\n" + "=" * 60)
