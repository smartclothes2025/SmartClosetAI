"""
下載並查看生成的穿搭圖片
"""
import urllib.request
import os
from datetime import datetime

# 最新生成的圖片 URL（照片編輯版提示詞）
image_url = "https://storage.googleapis.com/smartclothes_wardrobe/virtual_tryon_outfits_chat/20251122003514_bdf570e4.png"

# 下載圖片
output_dir = "test_results"
os.makedirs(output_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = os.path.join(output_dir, f"generated_{timestamp}.png")

print("下載生成的穿搭圖片...")
print(f"URL: {image_url}")
print(f"保存到: {output_path}")

try:
    urllib.request.urlretrieve(image_url, output_path)
    print(f"\n[SUCCESS] 圖片已下載: {output_path}")
    print(f"檔案大小: {os.path.getsize(output_path)} bytes")
    print("\n請手動開啟圖片查看：")
    print(f"   {os.path.abspath(output_path)}")
    print("\n檢查重點：")
    print("1. 臉部是否與用戶頭貼完全一致？")
    print("2. 身體是否穿著衣櫥裡的衣服？")
    print("3. 整體效果是否自然？")
    
    # 嘗試自動開啟圖片
    import subprocess
    subprocess.Popen(['explorer', os.path.abspath(output_path)])
    
except Exception as e:
    print(f"\n[ERROR] 下載失敗: {e}")
