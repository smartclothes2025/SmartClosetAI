#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試虛擬試衣功能 - 使用資料庫中的實際衣物
"""

import requests
import json
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# 資料庫連接
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/smartcloset")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_wardrobe_items(limit=5):
    """從資料庫獲取衣物清單"""
    db = SessionLocal()
    try:
        from app.models.wardrobe import WardrobeItem
        items = db.query(WardrobeItem).order_by(WardrobeItem.id.desc()).limit(limit).all()
        
        result = []
        for item in items:
            result.append({
                'id': item.id,
                'name': item.name,
                'category': item.category.value if item.category else '',
                'cover_image_url': item.cover_image_url
            })
        
        return result
    finally:
        db.close()

def test_virtual_fitting():
    """測試虛擬試衣 API"""
    
    print("=" * 60)
    print("虛擬試衣功能測試")
    print("=" * 60)
    
    # 1. 獲取資料庫中的衣物
    print("\n1️⃣ 從資料庫獲取衣物...")
    items = get_wardrobe_items(limit=10)
    
    if not items:
        print("❌ 資料庫中沒有衣物，請先上傳一些衣物")
        return
    
    print(f"✅ 找到 {len(items)} 件衣物")
    for item in items:
        print(f"   - ID={item['id']}, 名稱={item['name']}, 類別={item['category']}")
        print(f"     圖片 URL: {item['cover_image_url'][:80]}..." if item['cover_image_url'] else "     ⚠️ 無圖片")
    
    # 2. 選擇有圖片的衣物（選擇前 2 件）
    selected_items = []
    for item in items:
        if item['cover_image_url'] and item['cover_image_url'].startswith('gs://'):
            selected_items.append({
                'id': str(item['id']),
                'name': item['name'],
                'category': item['category'],
                'img': None  # ✅ 故意設為 None，測試 API 是否會從資料庫重新獲取
            })
            if len(selected_items) >= 2:
                break
    
    if len(selected_items) < 1:
        print("\n❌ 找不到有 GCS 圖片的衣物")
        print("請確保：")
        print("  1. 已上傳衣物到 GCS")
        print("  2. cover_image_url 欄位包含 gs:// 開頭的 URI")
        return
    
    print(f"\n2️⃣ 選擇 {len(selected_items)} 件衣物進行虛擬試衣")
    for item in selected_items:
        print(f"   - {item['name']} ({item['category']})")
    
    # 3. 呼叫虛擬試衣 API
    print("\n3️⃣ 呼叫虛擬試衣 API...")
    
    api_url = "http://127.0.0.1:8000/api/v1/fitting/generate"
    
    payload = {
        "user_input": "休閒日常穿搭",
        "selected_items": selected_items,
        "user_photo": None
    }
    
    print(f"   API URL: {api_url}")
    print(f"   請求內容: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(
            api_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=120  # 虛擬試衣可能需要較長時間
        )
        
        print(f"\n4️⃣ API 回應:")
        print(f"   狀態碼: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   回應類型: {data.get('type')}")
            
            if data.get('type') == 'image':
                print("   ✅ 成功生成圖片！")
                print(f"   圖片 URL 長度: {len(data.get('url', ''))} 字元")
                print(f"   使用的提示詞: {data.get('prompt_used', '')[:100]}...")
                
                # 儲存結果
                with open('fitting_test_result_with_db.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("\n   結果已儲存到: fitting_test_result_with_db.json")
                
            elif data.get('type') == 'text':
                print("   ⚠️ 返回文字說明（未生成圖片）")
                print(f"   說明: {data.get('text')}")
            
        else:
            print(f"   ❌ API 錯誤")
            print(f"   錯誤訊息: {response.text}")
    
    except requests.exceptions.Timeout:
        print("\n❌ 請求超時（超過 120 秒）")
        print("   虛擬試衣生成可能需要較長時間，請稍後再試")
    
    except requests.exceptions.ConnectionError:
        print("\n❌ 無法連接到後端服務")
        print("   請確認後端服務是否正在運行（http://127.0.0.1:8000）")
    
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_virtual_fitting()
