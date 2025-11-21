#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上傳 Style Shop 衣物圖片到 Google Cloud Storage
"""

import os
import sys
import json
from pathlib import Path
from google.cloud import storage
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\Users\Administrator\Desktop\SmartClosetAI\smartclothes-287af-9c1d1da8eb05.json'

# 配置
GCP_PROJECT_ID = "smartclothes-287af"
GCS_BUCKET_NAME = "smartclothes-styleshop"
STYLESHOP_IMAGES_DIR = r"C:\Users\Administrator\Desktop\網路商店\模擬網路商家衣物圖片"

# 初始化 GCS 客戶端
storage_client = storage.Client(project=GCP_PROJECT_ID)
bucket = storage_client.bucket(GCS_BUCKET_NAME)

def upload_images_from_directory(local_dir, gcs_prefix):
    """
    遞迴上傳目錄中的所有圖片到 GCS
    
    Args:
        local_dir: 本地目錄路徑
        gcs_prefix: GCS 中的前綴路徑 (e.g., "styleshop/women")
    
    Returns:
        dict: {文件名: 公開 URL}
    """
    uploaded_files = {}
    local_path = Path(local_dir)
    
    if not local_path.exists():
        print(f"❌ 目錄不存在: {local_dir}")
        return uploaded_files
    
    # 支援的圖片格式
    image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.jfif'}
    
    # 遞迴掃描所有圖片
    for file_path in local_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            try:
                # 計算相對路徑
                relative_path = file_path.relative_to(local_path)
                gcs_path = f"{gcs_prefix}/{relative_path}".replace("\\", "/")
                
                # 上傳檔案 (使用 predefined_acl 參數)
                blob = bucket.blob(gcs_path)
                blob.upload_from_filename(str(file_path), predefined_acl='publicRead')
                
                # 記錄公開 URL
                public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{gcs_path}"
                uploaded_files[str(relative_path).replace("\\", "/")] = public_url
                
                print(f"✅ 已上傳: {gcs_path}")
                
            except Exception as e:
                print(f"❌ 上傳失敗 {file_path}: {e}")
    
    return uploaded_files

def main():
    print("🚀 開始上傳 Style Shop 衣物圖片到 GCS...")
    print(f"📦 Bucket: {GCS_BUCKET_NAME}")
    print(f"📁 來源目錄: {STYLESHOP_IMAGES_DIR}\n")
    
    all_urls = {}
    
    # 上傳女生圖片
    print("👩 上傳女生衣物圖片...")
    women_dir = os.path.join(STYLESHOP_IMAGES_DIR, "女生")
    women_urls = upload_images_from_directory(women_dir, "styleshop/women")
    all_urls["women"] = women_urls
    print(f"✨ 女生圖片: {len(women_urls)} 張\n")
    
    # 上傳男生圖片
    print("👨 上傳男生衣物圖片...")
    men_dir = os.path.join(STYLESHOP_IMAGES_DIR, "男生")
    men_urls = upload_images_from_directory(men_dir, "styleshop/men")
    all_urls["men"] = men_urls
    print(f"✨ 男生圖片: {len(men_urls)} 張\n")
    
    # 保存配置文件
    config_file = os.path.join(os.path.dirname(__file__), "styleshop_images_config.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "project_id": GCP_PROJECT_ID,
            "bucket": GCS_BUCKET_NAME,
            "images": all_urls
        }, f, ensure_ascii=False, indent=2)
    
    print(f"📄 配置文件已保存: {config_file}")
    print(f"\n✅ 上傳完成！")
    print(f"   女生: {len(women_urls)} 張")
    print(f"   男生: {len(men_urls)} 張")
    print(f"   總計: {len(women_urls) + len(men_urls)} 張")

if __name__ == "__main__":
    main()
