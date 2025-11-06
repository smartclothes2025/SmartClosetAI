"""
測試虛擬試穿 API - 使用實際 GCS URI
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json

# API endpoint
url = "http://127.0.0.1:8000/api/v1/fitting/generate"

# 測試數據 - 使用實際的 GCS URI
test_data = {
    "user_input": "休閒時尚穿搭",
    "selected_items": [
        {
            "id": "ed3e7c32-6489-496c-acdd-238336df8ead",
            "name": "上衣",
            "category": "上衣",
            "img": "gs://smartclothes_wardrobe/wardrobe/9c33c7e9-ce22-4c4d-b385-15504ef368da/tops/上衣.jpg"
        },
        {
            "id": "62ea062b-21b8-4173-bb75-53935ae8c29e",
            "name": "裙子",
            "category": "裙子",
            "img": "gs://smartclothes_wardrobe/wardrobe/9c33c7e9-ce22-4c4d-b385-15504ef368da/skirts/裙子.jpg"
        }
    ]
}

print("=" * 80)
print("測試虛擬試穿 API - 使用 GCS URI")
print("=" * 80)
print(f"\nAPI URL: {url}")
print(f"\n選擇的衣物:")
for item in test_data["selected_items"]:
    print(f"  - {item['name']} ({item['category']})")
    print(f"    GCS URI: {item['img']}")

print("\n發送請求...")

try:
    response = requests.post(url, json=test_data, timeout=120)
    
    print(f"\nHTTP 狀態碼: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        
        print(f"\n回應類型: {result.get('type')}")
        
        if result.get('type') == 'image':
            url_length = len(result.get('url', ''))
            print(f"圖片 URL 長度: {url_length} 字元")
            print(f"提示訊息: {result.get('text', 'N/A')}")
            
            if url_length > 0:
                print("\n✅ 成功! 虛擬試穿圖片已生成")
                print("   圖片使用實際衣物圖片從 GCS 下載並生成")
                
                # 保存結果（不包含完整 base64）
                result_meta = {
                    "type": result.get("type"),
                    "has_url": True,
                    "url_length": url_length,
                    "text": result.get("text"),
                    "prompt_used": result.get("prompt_used")
                }
                with open("fitting_gcs_result.json", "w", encoding="utf-8") as f:
                    json.dump(result_meta, f, indent=2, ensure_ascii=False)
                print("   結果元數據已保存到: fitting_gcs_result.json")
            else:
                print("\n❌ 錯誤: 未收到圖片數據")
                
        elif result.get('type') == 'text':
            print(f"\n文字回應:")
            print(result.get('text', 'N/A'))
            
    else:
        print(f"\n❌ 請求失敗")
        print(f"錯誤: {response.text}")
        
except requests.exceptions.Timeout:
    print("\n❌ 請求超時 (>120秒)")
except Exception as e:
    print(f"\n❌ 錯誤: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
