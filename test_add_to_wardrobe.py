"""
測試品牌合作商品加入衣櫥功能
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 設定
API_BASE_URL = "http://localhost:8000"
TEST_PRODUCT_ID = 1  # 測試商品 ID

def get_test_token():
    """
    取得測試用 token
    請替換為實際的測試帳號
    """
    # 方法 1：從環境變數讀取
    token = os.getenv("TEST_USER_TOKEN")
    if token:
        return token
    
    # 方法 2：使用測試帳號登入
    login_data = {
        "username": "test@example.com",  # 替換為測試帳號
        "password": "testpassword"        # 替換為測試密碼
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/auth/login",
            json=login_data
        )
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"❌ 登入失敗: {e}")
        return None

def test_get_store_items():
    """測試 1：取得店家商品列表"""
    print("\n" + "="*60)
    print("測試 1：取得店家商品列表")
    print("="*60)
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/store/items",
            params={"gender": "women", "limit": 5}
        )
        response.raise_for_status()
        items = response.json()
        
        print(f"✅ 成功取得 {len(items)} 件商品")
        
        if items:
            print("\n商品範例：")
            item = items[0]
            print(f"  ID: {item.get('id')}")
            print(f"  名稱: {item.get('name')}")
            print(f"  類別: {item.get('category')}")
            print(f"  色系: {item.get('palette')}")
            print(f"  圖片: {item.get('imageUrl')[:80]}...")
            print(f"  購買連結: {item.get('purchaseUrl')}")
        
        return items
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None

def test_add_to_wardrobe(token, product_id):
    """測試 2：加入衣櫥"""
    print("\n" + "="*60)
    print(f"測試 2：將商品 {product_id} 加入衣櫥")
    print("="*60)
    
    if not token:
        print("❌ 沒有 token，跳過測試")
        return None
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/store/items/{product_id}/add-to-wardrobe",
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ {result.get('message')}")
        
        item = result.get('item', {})
        print(f"\n商品資訊：")
        print(f"  ID: {item.get('id')}")
        print(f"  名稱: {item.get('name')}")
        print(f"  類別: {item.get('category')}")
        print(f"  色系: {item.get('color')}")
        print(f"  來源: {item.get('source')}")
        print(f"  已存在: {item.get('already_exists')}")
        
        return result
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 錯誤: {e}")
        try:
            error_detail = e.response.json()
            print(f"   詳細訊息: {error_detail.get('detail')}")
        except:
            pass
        return None
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None

def test_duplicate_add(token, product_id):
    """測試 3：重複加入（應該顯示已存在）"""
    print("\n" + "="*60)
    print(f"測試 3：重複加入商品 {product_id}")
    print("="*60)
    
    if not token:
        print("❌ 沒有 token，跳過測試")
        return None
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/store/items/{product_id}/add-to-wardrobe",
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ {result.get('message')}")
        
        item = result.get('item', {})
        if item.get('already_exists'):
            print("✅ 正確檢測到商品已存在")
        else:
            print("⚠️ 警告：商品應該已存在但系統顯示為新增")
        
        return result
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None

def test_invalid_product_id(token):
    """測試 4：無效的商品 ID"""
    print("\n" + "="*60)
    print("測試 4：無效的商品 ID")
    print("="*60)
    
    if not token:
        print("❌ 沒有 token，跳過測試")
        return None
    
    invalid_id = 99999
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/store/items/{invalid_id}/add-to-wardrobe",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 404:
            print(f"✅ 正確返回 404 錯誤")
            error_detail = response.json()
            print(f"   錯誤訊息: {error_detail.get('detail')}")
        else:
            print(f"⚠️ 預期 404，但收到 {response.status_code}")
        
        return response
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None

def test_get_wardrobe_items(token):
    """測試 5：查看衣櫥中的商品"""
    print("\n" + "="*60)
    print("測試 5：查看衣櫥中的商品")
    print("="*60)
    
    if not token:
        print("❌ 沒有 token，跳過測試")
        return None
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/clothes/",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 50}
        )
        response.raise_for_status()
        items = response.json()
        
        print(f"✅ 衣櫥中共有 {len(items)} 件商品")
        
        # 找出來自店家的商品
        store_items = [
            item for item in items 
            if item.get('attributes', {}).get('source') == 'store'
        ]
        
        if store_items:
            print(f"\n來自品牌合作的商品 ({len(store_items)} 件)：")
            for item in store_items[:5]:  # 只顯示前 5 件
                print(f"  - {item.get('name')} ({item.get('category')})")
                print(f"    品牌: {item.get('brand')}")
                print(f"    標籤: {item.get('tags')}")
        else:
            print("⚠️ 衣櫥中沒有來自品牌合作的商品")
        
        return items
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return None

def main():
    """執行所有測試"""
    print("\n" + "="*60)
    print("品牌合作商品加入衣櫥功能測試")
    print("="*60)
    
    # 測試 1：取得店家商品
    items = test_get_store_items()
    
    # 取得測試 token
    print("\n" + "="*60)
    print("取得測試 token")
    print("="*60)
    token = get_test_token()
    
    if token:
        print(f"✅ Token: {token[:20]}...")
    else:
        print("❌ 無法取得 token")
        print("請設定環境變數 TEST_USER_TOKEN 或修改測試帳號")
        return
    
    # 確定測試商品 ID
    if items and len(items) > 0:
        test_product_id = items[0].get('id')
        print(f"\n使用商品 ID: {test_product_id}")
    else:
        test_product_id = TEST_PRODUCT_ID
        print(f"\n使用預設商品 ID: {test_product_id}")
    
    # 測試 2：加入衣櫥
    test_add_to_wardrobe(token, test_product_id)
    
    # 測試 3：重複加入
    test_duplicate_add(token, test_product_id)
    
    # 測試 4：無效 ID
    test_invalid_product_id(token)
    
    # 測試 5：查看衣櫥
    test_get_wardrobe_items(token)
    
    print("\n" + "="*60)
    print("測試完成")
    print("="*60)

if __name__ == "__main__":
    main()
