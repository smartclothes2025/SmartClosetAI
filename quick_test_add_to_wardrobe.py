"""
快速測試：品牌合作商品加入衣櫥
"""
import requests
import json

# 設定
API_BASE_URL = "http://localhost:8000"

print("=" * 60)
print("品牌合作商品加入衣櫥 - 快速測試")
print("=" * 60)

# 步驟 1：取得 token
print("\n請輸入您的認證 token (從瀏覽器開發者工具中取得):")
print("提示：在瀏覽器中按 F12 -> Application -> Local Storage -> 找到 token")
token = input("Token: ").strip()

if not token:
    print("❌ 未輸入 token，測試中止")
    exit(1)

# 步驟 2：測試取得店家商品
print("\n" + "=" * 60)
print("步驟 1：取得店家商品列表")
print("=" * 60)

try:
    response = requests.get(
        f"{API_BASE_URL}/api/v1/store/items",
        params={"gender": "women", "limit": 3}
    )
    response.raise_for_status()
    items = response.json()
    
    if not items:
        print("❌ 沒有找到店家商品")
        exit(1)
    
    print(f"✅ 找到 {len(items)} 件商品\n")
    
    for i, item in enumerate(items, 1):
        print(f"{i}. {item.get('name')}")
        print(f"   ID: {item.get('id')}")
        print(f"   類別: {item.get('category')}")
        print(f"   購買連結: {item.get('purchaseUrl')}\n")
    
    # 選擇第一個商品進行測試
    test_item = items[0]
    product_id = test_item.get('id')
    
except Exception as e:
    print(f"❌ 取得商品失敗: {e}")
    exit(1)

# 步驟 3：測試加入衣櫥
print("=" * 60)
print(f"步驟 2：將商品 {product_id} 加入衣櫥")
print("=" * 60)

try:
    response = requests.post(
        f"{API_BASE_URL}/api/v1/store/items/{product_id}/add-to-wardrobe",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"HTTP 狀態碼: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ {result.get('message')}\n")
        
        item = result.get('item', {})
        print("商品資訊：")
        print(f"  ID: {item.get('id')}")
        print(f"  名稱: {item.get('name')}")
        print(f"  類別: {item.get('category')}")
        print(f"  已存在: {item.get('already_exists')}")
        
    elif response.status_code == 401:
        print("❌ 認證失敗：Token 無效或已過期")
        print("請重新登入並取得新的 token")
        
    elif response.status_code == 404:
        error = response.json()
        print(f"❌ 找不到商品: {error.get('detail')}")
        
    else:
        error = response.json()
        print(f"❌ 錯誤: {error.get('detail')}")
        
except requests.exceptions.ConnectionError:
    print("❌ 無法連接到後端服務")
    print("請確認後端服務是否正在運行 (http://localhost:8000)")
    
except Exception as e:
    print(f"❌ 發生錯誤: {e}")

# 步驟 4：檢查衣櫥
print("\n" + "=" * 60)
print("步驟 3：檢查衣櫥中的商品")
print("=" * 60)

try:
    response = requests.get(
        f"{API_BASE_URL}/api/v1/clothes/",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 50}
    )
    response.raise_for_status()
    wardrobe_items = response.json()
    
    # 找出來自店家的商品
    store_items = [
        item for item in wardrobe_items 
        if item.get('attributes', {}).get('source') == 'store'
    ]
    
    if store_items:
        print(f"✅ 衣櫥中有 {len(store_items)} 件來自品牌合作的商品：\n")
        for item in store_items:
            print(f"  - {item.get('name')} ({item.get('category')})")
            print(f"    品牌: {item.get('brand')}")
            print(f"    商品 ID: {item.get('attributes', {}).get('product_id')}\n")
    else:
        print("⚠️ 衣櫥中沒有來自品牌合作的商品")
        
except Exception as e:
    print(f"❌ 檢查衣櫥失敗: {e}")

print("\n" + "=" * 60)
print("測試完成")
print("=" * 60)
