"""
測試圖片下載 - 診斷虛擬試衣圖片載入問題
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
from PIL import Image
from io import BytesIO

# 測試 URL
test_urls = [
    "https://storage.googleapis.com/smartclothes-287af.appspot.com/wardrobe_items/top1.jpg",
    "https://storage.googleapis.com/smartclothes-287af.appspot.com/wardrobe_items/skirt.jpg",
]

print("=" * 80)
print("測試圖片下載")
print("=" * 80)

for idx, url in enumerate(test_urls, 1):
    print(f"\n[{idx}] 測試 URL: {url}")
    print("-" * 80)
    
    try:
        # 嘗試下載
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
        
        print(f"✓ HTTP 狀態碼: {response.status_code}")
        print(f"✓ Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        print(f"✓ Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            # 嘗試解析圖片
            try:
                img = Image.open(BytesIO(response.content))
                print(f"✓ 圖片尺寸: {img.size[0]}x{img.size[1]}")
                print(f"✓ 圖片模式: {img.mode}")
                print(f"✓ 圖片格式: {img.format}")
                print("✅ 圖片下載和解析成功!")
            except Exception as img_error:
                print(f"❌ 無法解析圖片: {img_error}")
        else:
            print(f"❌ HTTP 錯誤: {response.status_code}")
            print(f"   回應內容: {response.text[:200]}")
            
    except requests.exceptions.Timeout:
        print("❌ 請求超時")
    except requests.exceptions.ConnectionError as e:
        print(f"❌ 連線錯誤: {e}")
    except Exception as e:
        print(f"❌ 錯誤: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("測試完成")
print("=" * 80)
