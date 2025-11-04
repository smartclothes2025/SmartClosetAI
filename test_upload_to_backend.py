#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""直接測試後端上傳 API"""

import requests
import io
from PIL import Image

print("=" * 60)
print("測試後端上傳 API")
print("=" * 60)

# 創建一個測試圖片
print("\n[1] 創建測試圖片...")
img = Image.new('RGB', (100, 100), color='red')
img_bytes = io.BytesIO()
img.save(img_bytes, format='JPEG')
img_bytes.seek(0)

# 準備上傳
url = "http://localhost:8000/api/v1/clothes"
files = {
    'file': ('test_gcs_upload.jpg', img_bytes, 'image/jpeg')
}
data = {
    'name': 'GCS測試上傳',
    'category': '上衣',
    'color': '紅色',
    'tags': '測試'
}

# 需要登入 token（如果需要的話）
# 你可能需要先登入獲取 token
headers = {}

print(f"\n[2] 發送請求到: {url}")
print(f"    檔名: test_gcs_upload.jpg")
print(f"    名稱: {data['name']}")

try:
    response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
    
    print(f"\n[3] 回應狀態: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"\n[成功] 上傳成功!")
        print(f"    ID: {result.get('id')}")
        print(f"    cover_image_url: {result.get('cover_image_url')}")
        
        cover_url = result.get('cover_image_url', '')
        if cover_url.startswith('gs://'):
            print(f"\n    [GCS] 已上傳到雲端!")
        elif cover_url.startswith('/uploads/'):
            print(f"\n    [本地] 存到本地儲存")
        else:
            print(f"\n    [未知] 位置: {cover_url}")
    else:
        print(f"\n[錯誤] 上傳失敗")
        print(f"    回應: {response.text}")
        
except Exception as e:
    print(f"\n[錯誤] 請求失敗: {e}")

print("\n" + "=" * 60)
print("請查看後端終端，應該會顯示:")
print("  [上傳] 開始處理: GCS測試上傳")
print("  [配置] USE_GCS=True, BUCKET=smartclothes_wardrobe")
print("  [GCS] 嘗試上傳至: ...")
print("  [成功] GCS 上傳成功: gs://...")
print("=" * 60)
