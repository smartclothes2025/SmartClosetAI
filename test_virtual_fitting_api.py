"""
測試虛擬試衣 API 端點
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_virtual_fitting_api():
    """測試虛擬試衣 API"""
    
    print("=" * 80)
    print("虛擬試衣 API 測試")
    print("=" * 80)
    
    # 測試數據
    test_data = {
        "user_input": "休閒日常穿搭",
        "selected_items": [
            {
                "id": 1,
                "name": "白色T恤",
                "category": "上衣",
                "img": None
            },
            {
                "id": 2,
                "name": "牛仔褲",
                "category": "褲子",
                "img": None
            }
        ],
        "user_photo": None,
        "body_metrics": {
            "height_cm": 170,
            "weight_kg": 60
        }
    }
    
    # 測試正確的 API 端點
    correct_url = f"{BASE_URL}/api/v1/fitting/generate"
    print(f"\n✅ 測試正確的 URL: {correct_url}")
    
    try:
        response = requests.post(
            correct_url,
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"狀態碼: {response.status_code}")
        print(f"響應內容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.status_code == 200:
            result = response.json()
            if result.get("type") == "text":
                print("\n⚠️ 返回文字響應（AI 服務未配置）")
            elif result.get("type") == "image":
                print("\n✅ 成功生成圖片")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    
    # 測試錯誤的 API 端點（重複 /api/v1）
    wrong_url = f"{BASE_URL}/api/v1/api/v1/fitting/generate"
    print(f"\n\n❌ 測試錯誤的 URL（重複 /api/v1）: {wrong_url}")
    
    try:
        response = requests.post(
            wrong_url,
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        print(f"狀態碼: {response.status_code}")
        print(f"響應: {response.text}")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    
    print("\n" + "=" * 80)
    print("測試完成")
    print("=" * 80)
    
    print("\n📋 修復建議：")
    print("1. 前端調用時 URL 重複了 /api/v1")
    print("2. 檢查前端代碼中的 API 配置")
    print("3. 正確的 URL 應該是: /api/v1/fitting/generate")
    print("4. 如果使用了 axios 或 fetch，檢查 baseURL 配置")
    print("\n示例修復：")
    print("   錯誤: axios.post('/api/v1/fitting/generate', data, { baseURL: 'http://127.0.0.1:8000/api/v1' })")
    print("   正確: axios.post('/fitting/generate', data, { baseURL: 'http://127.0.0.1:8000/api/v1' })")
    print("   或")
    print("   正確: axios.post('http://127.0.0.1:8000/api/v1/fitting/generate', data)")

if __name__ == "__main__":
    test_virtual_fitting_api()
