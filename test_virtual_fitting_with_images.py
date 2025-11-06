"""
測試虛擬試穿 API - 使用實際衣物圖片
"""
import requests
import json

# API endpoint
url = "http://127.0.0.1:8000/api/v1/fitting/generate"

# 測試數據 - 包含實際的圖片 URL
test_data = {
    "user_input": "休閒時尚穿搭",
    "selected_items": [
        {
            "id": "test-top-1",
            "name": "白色T恤",
            "category": "上衣",
            "img": "https://storage.googleapis.com/smartclothes-287af.appspot.com/wardrobe_items/top1.jpg"
        },
        {
            "id": "test-skirt-1",
            "name": "牛仔裙",
            "category": "裙子",
            "img": "https://storage.googleapis.com/smartclothes-287af.appspot.com/wardrobe_items/skirt.jpg"
        }
    ]
}

print("=" * 60)
print("Testing Virtual Fitting API with Clothing Images")
print("=" * 60)
print(f"\nURL: {url}")
print(f"\nSelected Items:")
for item in test_data["selected_items"]:
    print(f"  - {item['name']} ({item['category']})")
    print(f"    Image: {item['img']}")

print("\nSending request...")

try:
    response = requests.post(url, json=test_data, timeout=60)
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        
        # Save result
        with open("fitting_with_images_result.json", "w", encoding="utf-8") as f:
            # Don't save the full base64 image, just metadata
            result_meta = {
                "type": result.get("type"),
                "has_url": bool(result.get("url")),
                "url_length": len(result.get("url", "")),
                "prompt_used": result.get("prompt_used")
            }
            json.dump(result_meta, f, indent=2, ensure_ascii=False)
        
        print("\n[SUCCESS] Response metadata saved to: fitting_with_images_result.json")
        print(f"Response Type: {result.get('type')}")
        
        if result.get('type') == 'image':
            url_length = len(result.get('url', ''))
            print(f"Image URL Length: {url_length} characters")
            if url_length > 0:
                print("[SUCCESS] Image data received!")
                print("\nThe generated image should now match your selected clothing items.")
        elif result.get('type') == 'text':
            print("Text response received:")
            print(result.get('text', 'N/A')[:300])
            
    else:
        print(f"\n[FAILED] {response.text}")
        
except requests.exceptions.Timeout:
    print("\n[TIMEOUT] Request took too long (>60s)")
except Exception as e:
    print(f"\n[ERROR] {str(e)}")

print("\n" + "=" * 60)
