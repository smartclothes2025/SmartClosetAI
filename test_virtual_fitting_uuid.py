"""
測試虛擬試穿 API - 使用 UUID 格式的 ID
"""
import requests
import json

# API endpoint (注意：路由註冊時使用 /fitting 前綴)
url = "http://127.0.0.1:8000/api/v1/fitting/generate"

# 測試數據 - 使用 UUID 字串格式的 ID
test_data = {
    "user_input": "休閒時尚穿搭",
    "selected_items": [
        {
            "id": "fc4b06d8-59d2-4ab9-82d3-8df145d86dbc",
            "name": "白色T恤",
            "category": "上衣",
            "img": None
        },
        {
            "id": "abb7e357-b620-4813-8360-1e60d82a46ff",
            "name": "牛仔褲",
            "category": "褲子",
            "img": None
        }
    ]
}

print("發送請求到虛擬試穿 API...")
print(f"URL: {url}")
print(f"數據: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
print()

try:
    response = requests.post(url, json=test_data)
    
    print(f"狀態碼: {response.status_code}")
    print()
    
    if response.status_code == 200:
        result = response.json()
        print("[成功] 請求成功！")
        print(f"回應類型: {result.get('type')}")
        
        if result.get('type') == 'image':
            print(f"圖片 URL 長度: {len(result.get('url', ''))} 字元")
            print(f"使用的提示詞: {result.get('prompt_used', 'N/A')[:100]}...")
        elif result.get('type') == 'text':
            print(f"文字回應: {result.get('text', 'N/A')[:200]}...")
    else:
        print("[失敗] 請求失敗")
        print(f"錯誤: {response.text}")
        
except Exception as e:
    print(f"[錯誤] 發生錯誤: {str(e)}")
