"""測試今日推薦 API"""
import requests
import json

# 測試用戶 ID
user_id = "9c33c7e9-ce22-4c4d-b385-15504ef368da"

# 生成簡單的 token（根據你的 auth 邏輯）
token = f"user-{user_id}-token"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("="*80)
print("測試今日推薦 API")
print("="*80)

# 測試 /daily 端點
print("\n1. 測試 GET /api/v1/recommendations/daily")
print(f"   使用者: {user_id}")
print(f"   Token: {token}")

try:
    response = requests.get(
        "http://localhost:8000/api/v1/recommendations/daily",
        headers=headers
    )
    
    print(f"\n   狀態碼: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   找到 {len(data)} 筆推薦:\n")
        
        for rec in data:
            item = rec.get("item", {})
            print(f"   - {item.get('name')}")
            print(f"     類別: {item.get('category')}")
            print(f"     顏色: {item.get('color')}")
            print(f"     未穿天數: {item.get('daysInactive')} 天")
            print(f"     原因: {rec.get('reason')}")
            print(f"     圖片: {item.get('imageUrl')[:50]}..." if item.get('imageUrl') else "     圖片: 無")
            print()
    else:
        print(f"   錯誤: {response.text}")

except Exception as e:
    print(f"   發生錯誤: {e}")

# 測試 /inactive 端點
print("\n2. 測試 GET /api/v1/recommendations/inactive?days=90")

try:
    response = requests.get(
        "http://localhost:8000/api/v1/recommendations/inactive?days=90",
        headers=headers
    )
    
    print(f"\n   狀態碼: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"   找到 {len(data)} 件超過90天未穿的衣物\n")
        
        for rec in data:
            item = rec.get("item", {})
            print(f"   - {item.get('name')}")
            print(f"     類別: {item.get('category')}")
            print(f"     未穿天數: {item.get('daysInactive')} 天")
            print()
    else:
        print(f"   錯誤: {response.text}")

except Exception as e:
    print(f"   發生錯誤: {e}")

print("="*80)
