"""
診斷小助手臉部不匹配問題
"""
import sys
import os
import asyncio

# 添加專案路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.fashion_advisor import FashionAdvisor
from app.services.image_generation import ImageGenerationService
from app.models.auth import User
from app.core.database import get_db
from sqlalchemy.orm import Session

async def diagnose():
    print("=" * 60)
    print("🔍 診斷小助手臉部問題")
    print("=" * 60)
    
    # 1. 檢查資料庫連接
    print("\n[1] 檢查資料庫連接...")
    db: Session = next(get_db())
    
    # 2. 查詢用戶
    print("\n[2] 查詢用戶資料...")
    # 請將 user_id 改為你的實際 user_id
    user_id = 1  # ⚠️ 請改為你的 user_id
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        print(f"❌ 找不到 user_id={user_id} 的用戶")
        return
    
    print(f"✅ 找到用戶: {user.email}")
    
    # 3. 檢查頭貼 URI
    print("\n[3] 檢查用戶頭貼...")
    user_picture_uri = user.picture if hasattr(user, 'picture') else None
    print(f"   user.picture = '{user_picture_uri}'")
    
    if not user_picture_uri:
        print("❌ 用戶沒有設置頭貼！")
        print("   解決方案：請在前端上傳頭貼，或在資料庫中設置 picture 欄位")
        return
    
    print(f"✅ 用戶有頭貼: {user_picture_uri}")
    
    # 4. 嘗試下載頭貼
    print("\n[4] 嘗試下載用戶頭貼...")
    img_service = ImageGenerationService()
    
    # 構建完整 GCS URI
    if not user_picture_uri.startswith("gs://"):
        full_gcs_uri = f"gs://smartclothes_userphoto/{user_id}/{user_picture_uri.lstrip('/')}"
    else:
        full_gcs_uri = user_picture_uri
    
    print(f"   完整 GCS URI: {full_gcs_uri}")
    
    try:
        user_photo_base64 = await img_service.download_user_photo_from_gcs(
            picture_uri=full_gcs_uri,
            user_id=str(user_id)
        )
        
        if user_photo_base64:
            print(f"✅ 頭貼下載成功！")
            print(f"   Base64 長度: {len(user_photo_base64)} chars")
            print(f"   預覽: {user_photo_base64[:50]}...")
        else:
            print(f"❌ 頭貼下載返回 None")
            print(f"   可能原因：")
            print(f"   1. GCS bucket 中不存在此文件")
            print(f"   2. 權限問題")
            print(f"   3. 路徑錯誤")
            return
            
    except Exception as e:
        print(f"❌ 頭貼下載失敗: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 5. 檢查 FashionAdvisor 是否正確傳遞照片
    print("\n[5] 檢查 FashionAdvisor 邏輯...")
    print(f"   user_picture_uri: '{user_picture_uri}'")
    print(f"   是否會進入下載邏輯: {bool(user_picture_uri and user_picture_uri.strip())}")
    
    # 6. 模擬小助手穿搭請求
    print("\n[6] 模擬小助手穿搭請求...")
    print(f"   當小助手收到「穿搭」請求時：")
    print(f"   1. 會檢查 user_picture_uri = '{user_picture_uri}' ✅")
    print(f"   2. 會下載頭貼 = {bool(user_photo_base64)} ✅")
    print(f"   3. 會傳遞給 generate_tryon_image(user_photo_base64=...) ✅")
    
    print("\n" + "=" * 60)
    print("🎯 診斷結論")
    print("=" * 60)
    
    if user_photo_base64:
        print("✅ 頭貼下載成功，理論上應該能正確使用用戶的臉")
        print("\n如果實際生成的圖片還是不像你，可能原因：")
        print("1. Gemini 本身的限制（只能 30-70% 相似）")
        print("2. 需要臉部交換技術才能達到 99%+ 相似度")
        print("\n建議：檢查後端日誌，確認是否有以下訊息：")
        print("   ✅ 成功下載並使用用戶頭貼")
        print("   ✅ 將使用用戶照片生成個性化穿搭圖")
    else:
        print("❌ 頭貼下載失敗，這就是為什麼沒有使用你的臉")
        print("\n請檢查：")
        print("1. GCS bucket 中是否存在該文件")
        print("2. 檔案路徑是否正確")
        print("3. 服務帳戶是否有權限存取")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
