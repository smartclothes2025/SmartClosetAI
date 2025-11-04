#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""測試環境變數載入"""

import os
from dotenv import load_dotenv

# 明確載入 .env 文件
env_path = os.path.join(os.path.dirname(__file__), '.env')
print(f".env 檔案路徑: {env_path}")
print(f".env 檔案存在: {os.path.exists(env_path)}")

load_dotenv(env_path, override=True)

# 顯示相關環境變數
print("\n=== 環境變數檢查 ===")
print(f"GOOGLE_APPLICATION_CREDENTIALS = {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
print(f"GCP_PROJECT_ID = {os.getenv('GCP_PROJECT_ID')}")
print(f"GCP_LOCATION = {os.getenv('GCP_LOCATION')}")
print(f"DISABLE_VERTEX_AI = {os.getenv('DISABLE_VERTEX_AI')}")

# 檢查憑證檔案是否存在
cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if cred_path:
    print(f"\n憑證檔案存在: {os.path.exists(cred_path)}")
    if not os.path.exists(cred_path):
        print(f"  錯誤：找不到檔案 {cred_path}")
else:
    print("\n錯誤：GOOGLE_APPLICATION_CREDENTIALS 未設定")
