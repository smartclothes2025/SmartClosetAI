"""
測試虛擬試穿功能改進
Test Virtual Fitting Improvements

此腳本用於測試改進後的虛擬試穿功能，包括：
1. 檢查日誌輸出
2. 驗證生成方法追蹤
3. 測試不同衣物組合
"""

import asyncio
import sys
import os
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.image_generation import image_service
import logging

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_with_clothing_images():
    """測試使用實際衣物圖片生成"""
    
    print("\n" + "="*80)
    print("測試 1: 使用實際衣物圖片生成虛擬試穿圖")
    print("="*80 + "\n")
    
    # 模擬衣物數據（使用 GCS 上的實際圖片）
    clothing_items = [
        {
            "id": "test-top-1",
            "name": "白色襯衫",
            "category": "上衣",
            "img": "https://storage.googleapis.com/smartcloset-ai.appspot.com/uploads/tops/top_1.jpg"
        },
        {
            "id": "test-skirt-1",
            "name": "黑色裙子",
            "category": "裙子",
            "img": "https://storage.googleapis.com/smartcloset-ai.appspot.com/uploads/skirts/skirt_1.jpg"
        }
    ]
    
    prompt = "時尚日常穿搭，適合辦公室"
    
    try:
        result = await image_service.generate_tryon_image(
            prompt=prompt,
            style="realistic",
            width=768,
            height=1024,
            clothing_items=clothing_items
        )
        
        print("\n" + "="*80)
        print("測試結果")
        print("="*80)
        print(f"成功: {result.get('success')}")
        print(f"服務: {result.get('service', 'N/A')}")
        print(f"方法: {result.get('method', 'N/A')}")
        print(f"使用衣物圖片數量: {result.get('clothing_images_used', 0)}")
        
        if result.get('warning'):
            print(f"警告: {result.get('warning')}")
        
        if result.get('success'):
            image_size = len(result.get('image_base64', ''))
            print(f"圖片大小: {image_size / 1024:.1f} KB (base64)")
            print("\n✅ 測試通過：成功生成虛擬試穿圖片")
            
            # 檢查是否使用了實際衣物圖片
            if result.get('method') == 'multimodal_with_actual_clothing_images':
                print("✅ 確認：使用了實際衣物圖片")
            else:
                print(f"⚠️ 警告：使用了 fallback 方法 ({result.get('method')})")
        else:
            print(f"\n❌ 測試失敗：{result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 測試異常：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def test_text_only_fallback():
    """測試純文字生成 fallback"""
    
    print("\n" + "="*80)
    print("測試 2: 純文字生成 (無衣物圖片)")
    print("="*80 + "\n")
    
    prompt = "一位模特兒穿著白色襯衫和黑色裙子，專業時尚攝影"
    
    try:
        result = await image_service._generate_with_gemini_image(prompt)
        
        print("\n" + "="*80)
        print("測試結果")
        print("="*80)
        print(f"成功: {result.get('success')}")
        print(f"服務: {result.get('service', 'N/A')}")
        print(f"方法: {result.get('method', 'N/A')}")
        
        if result.get('warning'):
            print(f"警告: {result.get('warning')}")
        
        if result.get('success'):
            print("\n✅ 測試通過：純文字生成成功")
            
            if result.get('method') == 'text_only_fallback':
                print("✅ 確認：正確使用了 text_only_fallback 方法")
        else:
            print(f"\n❌ 測試失敗：{result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 測試異常：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def test_invalid_images():
    """測試無效圖片 URL 的處理"""
    
    print("\n" + "="*80)
    print("測試 3: 處理無效圖片 URL")
    print("="*80 + "\n")
    
    clothing_items = [
        {
            "id": "test-invalid-1",
            "name": "無效圖片",
            "category": "上衣",
            "img": "https://invalid-url.example.com/image.jpg"
        }
    ]
    
    prompt = "測試無效 URL"
    
    try:
        result = await image_service.generate_tryon_image(
            prompt=prompt,
            style="realistic",
            width=768,
            height=1024,
            clothing_items=clothing_items
        )
        
        print("\n" + "="*80)
        print("測試結果")
        print("="*80)
        print(f"成功: {result.get('success')}")
        print(f"方法: {result.get('method', 'N/A')}")
        
        # 應該回退到純文字生成
        if result.get('method') == 'text_only_fallback':
            print("\n✅ 測試通過：正確回退到純文字生成")
        elif result.get('success'):
            print("\n⚠️ 警告：雖然成功，但預期應該使用 fallback")
        else:
            print(f"\n❌ 測試失敗：{result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 測試異常：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def test_category_mapping():
    """測試類別映射功能"""
    
    print("\n" + "="*80)
    print("測試 4: 類別映射 (中英文支援)")
    print("="*80 + "\n")
    
    clothing_items = [
        {
            "id": "test-1",
            "name": "上衣測試",
            "category": "上衣",  # 中文
            "img": "https://storage.googleapis.com/smartcloset-ai.appspot.com/uploads/tops/top_1.jpg"
        },
        {
            "id": "test-2",
            "name": "Skirt Test",
            "category": "skirt",  # 英文小寫
            "img": "https://storage.googleapis.com/smartcloset-ai.appspot.com/uploads/skirts/skirt_1.jpg"
        }
    ]
    
    prompt = "測試類別映射"
    
    try:
        # 直接調用內部方法以檢查類別處理
        result = await image_service._generate_with_clothing_images(
            prompt=prompt,
            clothing_items=clothing_items
        )
        
        print("\n" + "="*80)
        print("測試結果")
        print("="*80)
        
        if result.get('success'):
            print("✅ 測試通過：類別映射正常工作")
            print(f"使用衣物圖片數量: {result.get('clothing_images_used', 0)}")
        else:
            print(f"⚠️ 測試結果：{result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 測試異常：{str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """運行所有測試"""
    
    print("\n" + "="*80)
    print("虛擬試穿功能改進測試套件")
    print("="*80)
    
    # 檢查 API Key
    if not os.getenv("GEMINI_API_KEY"):
        print("\n❌ 錯誤：未設置 GEMINI_API_KEY 環境變數")
        print("請在 .env 文件中設置 GEMINI_API_KEY")
        return
    
    print(f"\n✅ GEMINI_API_KEY 已設置")
    
    # 運行測試
    results = []
    
    # 測試 1: 使用實際衣物圖片
    result1 = await test_with_clothing_images()
    results.append(("使用實際衣物圖片", result1))
    
    await asyncio.sleep(2)  # 避免 API 限流
    
    # 測試 2: 純文字生成
    result2 = await test_text_only_fallback()
    results.append(("純文字生成", result2))
    
    await asyncio.sleep(2)
    
    # 測試 3: 無效圖片 URL
    result3 = await test_invalid_images()
    results.append(("無效圖片 URL", result3))
    
    await asyncio.sleep(2)
    
    # 測試 4: 類別映射
    result4 = await test_category_mapping()
    results.append(("類別映射", result4))
    
    # 總結
    print("\n" + "="*80)
    print("測試總結")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        if result and result.get('success'):
            print(f"✅ {test_name}: 通過")
            passed += 1
        else:
            print(f"❌ {test_name}: 失敗")
            failed += 1
    
    print(f"\n總計: {passed} 通過, {failed} 失敗")
    
    if failed == 0:
        print("\n🎉 所有測試通過！")
    else:
        print(f"\n⚠️ 有 {failed} 個測試失敗，請檢查日誌")


if __name__ == "__main__":
    asyncio.run(main())
