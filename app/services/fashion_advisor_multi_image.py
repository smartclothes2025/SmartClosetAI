# app/services/fashion_advisor_multi_image.py
# 🔥 多圖片處理邏輯的新方法（將整合到 fashion_advisor.py）

import logging
from typing import Dict, List, Optional, Any
import base64
from io import BytesIO
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

async def process_user_input_with_multi_images(
    self,
    user_id: str,
    user_input: str,
    user_images: Optional[List[str]] = None,  # 🔥 改為列表，最多 3 張圖片
    picture_uri: Optional[str] = None,
    user_gender: Optional[str] = None
) -> Dict[str, Any]:
    """
    處理小助手的用戶輸入（聊天頁面）- 支援多圖片上傳
    
    Args:
        user_id: 用戶 ID
        user_input: 用戶輸入的文字
        user_images: 前端上傳的照片列表 (base64)，最多 3 張
        picture_uri: 用戶頭貼 URI
        user_gender: 用戶性別
        
    四種圖片組合策略：
        1. 如果上傳臉部 -> 根據用戶上傳的臉部 + 現有衣櫥的兩件衣物 -> 生成穿搭圖
        2. 如果上傳衣物 -> 根據用戶上傳的衣物 + 用戶頭貼 -> 生成穿搭圖
        3. 如果上傳衣物+臉部 -> 根據用戶上傳的衣物 + 用戶上傳的臉部 -> 生成穿搭圖
        4. 如果沒有上傳圖片 -> 根據用戶頭貼 + 衣櫥內現有衣物 -> 生成穿搭圖
    """
    from .image_classifier import image_classifier
    from .image_generation import image_service as img_gen_service
    from .weather_service import weather_service
    
    logger.info(f"🤖 小助手處理請求：User ID: {user_id}")
    logger.info(f"   輸入: {user_input}")
    logger.info(f"   上傳圖片數量: {len(user_images) if user_images else 0}")
    
    # 1. 獲取天氣資訊
    weather_info = None
    weather_advice = ""
    try:
        if weather_service:
            weather_info = await weather_service.get_weather_info(city="Taoyuan")
            if weather_info:
                temp = weather_info.get("temperature", 20)
                weather_advice = weather_info.get("suggestion", "")
                logger.info(f"🌤️ 天氣資訊：{weather_info['city']} {temp}°C - {weather_info.get('weather_description', '')}")
    except Exception as e:
        logger.warning(f"獲取天氣資訊失敗: {e}")
    
    # 2. 獲取用戶衣櫃
    wardrobe_items = self.get_wardrobe_items(user_id)
    logger.info(f"👔 獲取到 {len(wardrobe_items)} 件衣物")
    
    # 3. 🔥 分類上傳的圖片（臉部 vs 衣物）
    face_images = []
    clothing_images = []
    
    if user_images and len(user_images) > 0:
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 開始分類上傳的圖片...")
        logger.info(f"{'='*60}\n")
        
        classified_result = image_classifier.classify_images(user_images)
        
        face_images = classified_result.get("face_images", [])
        clothing_images = classified_result.get("clothing_images", [])
        unknown_images = classified_result.get("unknown_images", [])
        
        logger.info(f"\n📊 分類結果總結:")
        logger.info(f"   臉部照片: {len(face_images)} 張")
        logger.info(f"   衣物照片: {len(clothing_images)} 張")
        logger.info(f"   無法判斷: {len(unknown_images)} 張")
        
        # 將無法判斷的圖片暫時視為衣物（保守策略）
        if unknown_images:
            logger.info(f"   ℹ️ 將 {len(unknown_images)} 張無法判斷的圖片視為衣物")
            clothing_images.extend(unknown_images)
    
    # 4. 🔥 決定照片和衣物來源（四種策略）
    final_face_photo = None
    final_clothing_items = []
    photo_source = ""
    strategy = ""
    
    # 策略判斷
    has_uploaded_face = len(face_images) > 0
    has_uploaded_clothing = len(clothing_images) > 0
    
    if has_uploaded_face and has_uploaded_clothing:
        # 策略 3: 上傳衣物 + 臉部
        strategy = "策略3: 上傳衣物 + 臉部"
        final_face_photo = face_images[0]  # 使用第一張臉部照片
        photo_source = "前端上傳臉部照片"
        
        # 衣物來源：上傳的衣物圖片（最多2張）
        final_clothing_items = [
            {"name": f"上傳衣物_{idx+1}", "category": "tops", "img": img}
            for idx, img in enumerate(clothing_images[:2])
        ]
        logger.info(f"✅ {strategy}")
        logger.info(f"   臉部: 使用上傳照片")
        logger.info(f"   衣物: 使用 {len(final_clothing_items)} 件上傳衣物")
        
    elif has_uploaded_face and not has_uploaded_clothing:
        # 策略 1: 上傳臉部 + 衣櫥衣物
        strategy = "策略1: 上傳臉部 + 衣櫥衣物"
        final_face_photo = face_images[0]
        photo_source = "前端上傳臉部照片"
        
        # 衣物來源：從衣櫥隨機選擇2件
        clothing_dicts = [
            {"name": item.name, "category": item.category, "img": item.cover_image_url}
            for item in wardrobe_items if item.cover_image_url
        ]
        if len(clothing_dicts) > 2:
            final_clothing_items = self._smart_select_clothing_items(clothing_dicts, max_items=2)
        else:
            final_clothing_items = clothing_dicts
        
        logger.info(f"✅ {strategy}")
        logger.info(f"   臉部: 使用上傳照片")
        logger.info(f"   衣物: 從衣櫥選擇 {len(final_clothing_items)} 件")
        
    elif not has_uploaded_face and has_uploaded_clothing:
        # 策略 2: 上傳衣物 + 用戶頭貼
        strategy = "策略2: 上傳衣物 + 用戶頭貼"
        
        # 臉部來源：嘗試下載用戶頭貼
        if picture_uri and picture_uri.strip():
            try:
                final_face_photo = await img_gen_service.download_user_photo_from_gcs(
                    picture_uri, str(user_id)
                )
                if final_face_photo:
                    photo_source = "用戶頭貼"
                    logger.info(f"✅ 成功下載用戶頭貼")
                else:
                    photo_source = "預設模特兒（頭貼下載失敗）"
                    logger.warning(f"⚠️ 用戶頭貼下載返回 None")
            except Exception as e:
                logger.error(f"❌ 用戶頭貼下載異常: {e}")
                photo_source = "預設模特兒（下載異常）"
        else:
            photo_source = "預設模特兒（無頭貼）"
        
        # 衣物來源：上傳的衣物圖片（最多2張）
        final_clothing_items = [
            {"name": f"上傳衣物_{idx+1}", "category": "tops", "img": img}
            for idx, img in enumerate(clothing_images[:2])
        ]
        
        logger.info(f"✅ {strategy}")
        logger.info(f"   臉部: {photo_source}")
        logger.info(f"   衣物: 使用 {len(final_clothing_items)} 件上傳衣物")
        
    else:
        # 策略 4: 用戶頭貼 + 衣櫥衣物（原有功能）
        strategy = "策略4: 用戶頭貼 + 衣櫥衣物"
        
        # 臉部來源：嘗試下載用戶頭貼
        if picture_uri and picture_uri.strip():
            try:
                final_face_photo = await img_gen_service.download_user_photo_from_gcs(
                    picture_uri, str(user_id)
                )
                if final_face_photo:
                    photo_source = "用戶頭貼"
                else:
                    photo_source = "預設模特兒（頭貼下載失敗）"
            except Exception as e:
                logger.error(f"❌ 用戶頭貼下載異常: {e}")
                photo_source = "預設模特兒（下載異常）"
        else:
            photo_source = "預設模特兒（無頭貼）"
        
        # 衣物來源：從衣櫥隨機選擇2件
        clothing_dicts = [
            {"name": item.name, "category": item.category, "img": item.cover_image_url}
            for item in wardrobe_items if item.cover_image_url
        ]
        if len(clothing_dicts) > 2:
            final_clothing_items = self._smart_select_clothing_items(clothing_dicts, max_items=2)
        else:
            final_clothing_items = clothing_dicts
        
        logger.info(f"✅ {strategy}")
        logger.info(f"   臉部: {photo_source}")
        logger.info(f"   衣物: 從衣櫥選擇 {len(final_clothing_items)} 件")
    
    # 最終決策確認
    logger.info(f"\n{'='*60}")
    logger.info(f"📸 最終組合決策:")
    logger.info(f"    策略: {strategy}")
    logger.info(f"    照片來源: {photo_source}")
    logger.info(f"    是否有用戶照片: {'是' if final_face_photo else '否'}")
    logger.info(f"    衣物數量: {len(final_clothing_items)}")
    logger.info(f"    用戶性別: {user_gender or '未提供 (預設 women)'}")
    logger.info(f"{'='*60}\n")
    
    # 5. 處理請求類型（與原有邏輯相同）
    try:
        # 1️⃣ 檢查是否只詢問天氣
        if self.is_weather_only_request(user_input):
            logger.info("🌤️ 偵測到純天氣查詢，返回天氣資訊。")
            if weather_info:
                weather_text = f"""📍 {weather_info['city']} 的天氣資訊：

🌡️ 溫度：{weather_info['temperature']}°C（體感 {weather_info['feels_like']}°C）
☁️ 天氣：{weather_info['weather_description']}
💧 濕度：{weather_info['humidity']}%
💨 風速：{weather_info['wind_speed']} m/s

{weather_advice}"""
                return {"type": "text", "text": weather_text}
            else:
                return {"type": "text", "text": "抱歉，目前無法獲取天氣資訊，請稍後再試。"}
        
        # 2️⃣ 檢查是否為穿搭請求
        if self.is_outfit_request(user_input):
            logger.info("👗 偵測到穿搭請求，執行虛擬試穿。")
            
            if not final_clothing_items:
                logger.warning("沒有可用的衣物，無法生成穿搭圖")
                return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
            
            # 使用 ImageGenerationService 生成穿搭圖
            logger.info(f"🛠️ 準備呼叫 img_gen_service.generate_tryon_image()")
            logger.info(f"    📸 照片來源: {photo_source}")
            logger.info(f"    📸 是否傳遞用戶照片: {'是' if final_face_photo else '否'}")
            logger.info(f"    👔 衣物數量: {len(final_clothing_items)}")
            
            generation_result = await img_gen_service.generate_tryon_image(
                prompt=user_input,
                clothing_items=final_clothing_items,
                user_photo_base64=final_face_photo
            )
            
            if generation_result.get("success"):
                image_base64 = generation_result.get("image_base64")
                
                if image_base64:
                    logger.info(f"🖼️ 成功取得生成圖片，長度: {len(image_base64)} characters，開始上傳 GCS。")
                    image_bytes = base64.b64decode(image_base64)
                    generated_image_url = self._upload_image_to_gcs(image_bytes, folder="virtual_tryon_outfits_chat")
                else:
                    generated_image_url = None
                
                if generated_image_url:
                    logger.info(f"✅ 影像已生成並上傳，URL: {generated_image_url}")
                    
                    response_text = f"""好的，這是為您生成的穿搭建議

📸 使用策略: {strategy}
📷 照片來源: {photo_source}
👔 衣物來源: {len(final_clothing_items)} 件{"上傳衣物" if has_uploaded_clothing else "衣櫥衣物"}"""
                    
                    return {
                        "type": "image",
                        "url": generated_image_url,
                        "text": response_text
                    }
                else:
                    logger.error("虛擬試穿成功但 GCS 上傳失敗，轉為文字回覆。")
                    return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
            else:
                logger.error(f"虛擬試穿失敗: {generation_result.get('error', '未知錯誤')}，轉為文字回覆。")
                return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
        
        # 3️⃣ 其他問題：一般聊天
        logger.info("💬 非穿搭/天氣請求，調用 Gemini 生成智能回覆")
        return self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)
    
    except Exception as e:
        logger.error(f"處理用戶輸入時發生錯誤: {str(e)}", exc_info=True)
        return {"type": "text", "text": f"抱歉，處理您的請求時發生錯誤：{str(e)}"}
