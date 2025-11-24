"""
測試小助手（FashionAdvisor）的照片下載邏輯
"""
import asyncio
import sys
import os

# 添加專案路徑
sys.path.insert(0, os.path.dirname(__file__))

async def test_chat_photo_logic():
    print("="*60)
    print("Test FashionAdvisor Photo Download")
    print("="*60)
    
    # 1. Test user data retrieval
    from app.core.db import get_db
    from app.models.auth import User
    from sqlalchemy import text
    
    db = next(get_db())
    
    print("\n[1] Query user data...")
    users = db.query(User).limit(5).all()
    
    if not users:
        print("[ERROR] No users found")
        return
    
    for user in users:
        username = getattr(user, 'username', getattr(user, 'email', 'Unknown'))
        print(f"\nUser: {username} (ID: {user.id})")
        print(f"  Email: {getattr(user, 'email', 'N/A')}")
        print(f"  Picture URI: {user.picture if hasattr(user, 'picture') else 'None'}")
    
    # Select first user with picture
    test_user = None
    for user in users:
        if hasattr(user, 'picture') and user.picture:
            test_user = user
            break
    
    if not test_user:
        print("\n[ERROR] No user with picture found")
        return
    
    test_username = getattr(test_user, 'username', getattr(test_user, 'email', 'Unknown'))
    print(f"\n[OK] Test user: {test_username}")
    print(f"     Picture URI: {test_user.picture}")
    
    # 2. Test photo download
    print("\n[2] Test photo download...")
    from app.services.image_generation import image_service
    
    try:
        photo_base64 = await image_service.download_user_photo_from_gcs(
            test_user.picture,
            str(test_user.id)
        )
        
        if photo_base64:
            print(f"[OK] Photo downloaded!")
            print(f"     Base64 length: {len(photo_base64)} chars")
            print(f"     Base64 preview: {photo_base64[:50]}...")
        else:
            print("[ERROR] Photo download returned None")
            
    except Exception as e:
        print(f"[ERROR] Photo download failed: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. Test complete flow
    print("\n[3] Test complete flow (no image generation)...")
    from app.services.fashion_advisor import FashionAdvisor
    
    advisor = FashionAdvisor()
    
    print(f"     user_id: {test_user.id}")
    print(f"     user_picture_uri: {test_user.picture}")
    print(f"     test input: 'recommend today outfit'")
    
    # Only test photo download, no actual generation
    print("\n[OK] If photo download succeeded above, logic is correct")
    print("     Check actual API call logs for details")

if __name__ == "__main__":
    asyncio.run(test_chat_photo_logic())
