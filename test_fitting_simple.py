"""
簡單的虛擬試穿 API 測試 - 結果保存到檔案
"""
import requests
import json

# API endpoint
url = "http://127.0.0.1:8000/api/v1/fitting/generate"

# 測試數據
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

print("Testing Virtual Fitting API...")
print(f"URL: {url}")

try:
    response = requests.post(url, json=test_data)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        
        # 保存結果到檔案
        with open("fitting_test_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print("SUCCESS! Response saved to: fitting_test_result.json")
        print(f"Response Type: {result.get('type')}")
        
        if result.get('type') == 'image':
            url_length = len(result.get('url', ''))
            print(f"Image URL Length: {url_length} characters")
            if url_length > 0:
                print("Image data received successfully!")
        elif result.get('type') == 'text':
            print("Text response received")
            
    else:
        print(f"FAILED: {response.text}")
        
except Exception as e:
    print(f"ERROR: {str(e)}")
