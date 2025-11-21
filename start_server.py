#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""後端啟動腳本"""

import os
import sys

print("=" * 60)
print("正在啟動 SmartClosetAI 後端...")
print("=" * 60)

# 確保在正確的目錄
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 檢查必要文件
print("\n[檢查] 必要文件...")
required_files = [".env", "app/main.py", "app/api/v1/router.py"]
for file in required_files:
    if os.path.exists(file):
        print(f"  [OK] {file}")
    else:
        print(f"  [ERROR] {file} 不存在!")
        sys.exit(1)

# 檢查 GCP 憑證
from dotenv import load_dotenv
load_dotenv()

gcp_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if gcp_cred:
    if os.path.exists(gcp_cred):
        print(f"  [OK] GCP 憑證: {gcp_cred}")
    else:
        print(f"  [WARNING] GCP 憑證文件不存在: {gcp_cred}")
        print(f"    某些功能可能無法使用")

# 嘗試導入應用
print("\n[載入] FastAPI 應用...")
try:
    from app.main import app
    print(f"  [OK] 應用載入成功")
    print(f"  應用標題: {app.title}")
    print(f"  已註冊路由: {len(app.routes)} 個")
except Exception as e:
    print(f"  [ERROR] 應用載入失敗!")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 啟動服務器
if __name__ == '__main__':
    print("\n[啟動] Uvicorn 服務器...")
    print("  地址: http://0.0.0.0:8077")
    print("  文檔: http://localhost:8077/docs")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    
    import uvicorn
    # 啟用詳細日誌，確保所有請求都會顯示
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8077,
        reload=True,
        log_level="info",  # 設定日誌級別為 info
        access_log=True,   # 啟用訪問日誌
        use_colors=True    # 使用彩色輸出
    )
