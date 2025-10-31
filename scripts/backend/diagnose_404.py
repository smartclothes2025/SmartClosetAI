"""
快速測試通知 API 是否可訪問
"""

import requests

BASE_URL = "http://localhost:8000"

print("="*80)
print("通知 API 404 錯誤診斷")
print("="*80)

# 測試 1: 檢查後端是否運行
print("\n1️⃣ 檢查後端是否運行...")
try:
    response = requests.get(f"{BASE_URL}/docs", timeout=3)
    if response.status_code == 200:
        print("   ✅ 後端正在運行")
    else:
        print(f"   ⚠️  後端回應異常: {response.status_code}")
except requests.exceptions.ConnectionError:
    print("   ❌ 無法連接到後端！")
    print("   請執行: python start_server.py")
    exit(1)
except Exception as e:
    print(f"   ❌ 錯誤: {e}")
    exit(1)

# 測試 2: 檢查通知路由
print("\n2️⃣ 檢查通知 API 路由...")

test_endpoints = [
    ("GET", f"{BASE_URL}/api/v1/notifications/?user_id=1", "獲取通知列表"),
    ("POST", f"{BASE_URL}/api/v1/notifications/", "建立通知"),
]

for method, url, desc in test_endpoints:
    try:
        if method == "GET":
            response = requests.get(
                url,
                headers={"Authorization": "Bearer user-1-token"},
                timeout=3
            )
        else:
            response = requests.post(
                url,
                headers={
                    "Authorization": "Bearer user-1-token",
                    "Content-Type": "application/json"
                },
                json={
                    "user_id": "1",
                    "type": "test",
                    "message": "測試",
                    "payload": {"test": True}
                },
                timeout=3
            )
        
        if response.status_code == 404:
            print(f"   ❌ {method} {url}")
            print(f"      {desc} - 404 Not Found")
            print(f"      問題：路由未註冊或路徑錯誤")
        elif response.status_code in [200, 201]:
            print(f"   ✅ {method} {url}")
            print(f"      {desc} - 成功")
        elif response.status_code == 401:
            print(f"   ⚠️  {method} {url}")
            print(f"      {desc} - 401 Unauthorized (認證問題，但路由存在)")
        else:
            print(f"   ⚠️  {method} {url}")
            print(f"      {desc} - {response.status_code} {response.reason}")
            
    except Exception as e:
        print(f"   ❌ {method} {url}")
        print(f"      錯誤: {e}")

# 測試 3: 列出所有可用路由
print("\n3️⃣ 檢查 OpenAPI 規範...")
try:
    response = requests.get(f"{BASE_URL}/openapi.json", timeout=3)
    if response.status_code == 200:
        openapi = response.json()
        paths = openapi.get("paths", {})
        
        notification_routes = [path for path in paths.keys() if "notification" in path.lower()]
        
        if notification_routes:
            print("   ✅ 找到通知相關路由:")
            for route in notification_routes:
                methods = list(paths[route].keys())
                print(f"      - {route} ({', '.join(methods).upper()})")
        else:
            print("   ❌ 未找到通知相關路由！")
            print("      可能原因：")
            print("      1. notifications router 未在 app/api/v1/router.py 中註冊")
            print("      2. 後端需要重啟")
    else:
        print(f"   ⚠️  無法獲取 OpenAPI 規範: {response.status_code}")
except Exception as e:
    print(f"   ❌ 錯誤: {e}")

# 總結
print("\n" + "="*80)
print("診斷總結")
print("="*80)

print("\n如果看到 404 錯誤，請檢查：")
print("1. 前端請求的 URL 是否包含 /api/v1 前綴")
print("   正確: http://localhost:8000/api/v1/notifications/")
print("   錯誤: http://localhost:8000/notifications/")
print()
print("2. 前端的 API_BASE 設定是否正確")
print("   const API_BASE = 'http://localhost:8000'")
print()
print("3. 後端路由是否已註冊（檢查 app/api/v1/router.py）")
print("   api_router.include_router(notifications_router, prefix=\"/notifications\")")
print()
print("4. 後端伺服器是否已重啟以載入路由")

print("\n" + "="*80)
