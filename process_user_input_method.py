    async def process_user_input(
        self, 
        user_id: str, 
        user_input: str, 
        user_image_data: Optional[str] = None,
        picture_uri: Optional[str] = None,
        user_gender: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        處理小助手的用戶輸入（聊天頁面）
        
        Args:
            user_id: 用戶 ID
            user_input: 用戶輸入的文字
            user_image_data: 前端上傳的照片 (base64)
            picture_uri: 用戶頭貼 URI
            user_gender: 用戶性別
        """
        logger.info(f"🤖 小助手處理請求：User ID: {user_id}")
        logger.info(f"   輸入: {user_input}")
        
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
        
        # 3. 處理照片優先級
        user_photo_base64 = None
        photo_source = "預設模特兒"
        
        # 優先級 1: 前端上傳的照片
        if user_image_data:
            logger.info("📸 優先級 1: 處理前端上傳照片")
            # 移除 Data URI Scheme
            if user_image_data.startswith("data:image"):
                user_image_data = (
                    user_image_data.split(",", 1)[1]
                    if "," in user_image_data
                    else user_image_data
                )
                logger.info("✅ 已移除 Data URI Scheme 前綴")
            
            try:
                user_photo_base64 = user_image_data
                photo_source = "上傳照片"
                logger.info(f"✅ 成功載入上傳照片，長度: {len(user_photo_base64)} chars")
            except Exception as e:
                logger.warning(f"⚠️ 上傳照片處理失敗: {e}")
                user_photo_base64 = None
        
        # 優先級 2: 用戶頭貼
        if not user_photo_base64 and picture_uri and picture_uri.strip():
            logger.info(f"📸 優先級 2: 下載用戶頭貼")
            try:
                user_photo_base64 = await img_gen_service.download_user_photo_from_gcs(
                    picture_uri,
                    str(user_id)
                )
                if user_photo_base64:
                    photo_source = "用戶頭貼"
                    logger.info(f"✅ 成功下載用戶頭貼，長度: {len(user_photo_base64)} chars")
                else:
                    logger.warning("⚠️ 用戶頭貼下載返回 None")
            except Exception as e:
                logger.warning(f"⚠️ 用戶頭貼下載失敗: {e}")
        
        # 優先級 3: 預設模特兒
        if not user_photo_base64:
            logger.info("📸 優先級 3: 使用預設模特兒")
            photo_source = "預設模特兒"
        
        logger.info(f"🎯 最終照片來源: {photo_source}")
        
        # 4. 檢查請求類型並處理
        try:
            # 只詢問天氣
            if self.is_weather_only_request(user_input):
                logger.info("🌤️ 偵測到純天氣查詢")
                if weather_info:
                    weather_text = f"""📍 {weather_info['city']} 的天氣資訊：

🌡️ 溫度：{weather_info['temperature']}°C（體感 {weather_info.get('feels_like', weather_info['temperature'])}°C）
☁️ 天氣：{weather_info.get('weather_description', '未知')}
💧 濕度：{weather_info.get('humidity', 'N/A')}%
💨 風速：{weather_info.get('wind_speed', 'N/A')} m/s

{weather_advice}"""
                    return {"type": "text", "text": weather_text}
                else:
                    return {"type": "text", "text": "抱歉，目前無法獲取天氣資訊，請稍後再試。"}
            
            # 穿搭請求
            if self.is_outfit_request(user_input):
                logger.info("👗 偵測到穿搭請求")
                
                if not wardrobe_items:
                    return {"type": "text", "text": "您的衣櫃目前是空的，請先上傳一些衣物照片，我才能為您提供穿搭建議！"}
                
                # 轉換為字典格式
                clothing_dicts = [
                    {"name": item.name, "category": item.category, "img": item.cover_image_url}
                    for item in wardrobe_items if item.cover_image_url
                ]
                logger.info(f"🧾 從衣櫃整理出 {len(clothing_dicts)} 件含圖片的衣物")
                
                # 智能隨機挑選 2 件衣物
                if len(clothing_dicts) > 2:
                    logger.info(f"⚠️ 衣物數量 ({len(clothing_dicts)}) 超過 2 件，開始智能隨機挑選")
                    clothing_dicts = self._smart_select_clothing_items(clothing_dicts, max_items=2)
                    logger.info(f"✅ 已智能挑選 {len(clothing_dicts)} 件衣物")
                elif len(clothing_dicts) < 2:
                    logger.info(f"ℹ️ 衣物數量 ({len(clothing_dicts)}) 少於 2 件，使用所有衣物")
                else:
                    logger.info(f"✅ 衣物數量剛好 2 件")
                
                if not clothing_dicts:
                    return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
                
                # 生成穿搭圖
                logger.info("🛠️ 準備呼叫 img_gen_service.generate_tryon_image()")
                generation_result = await img_gen_service.generate_tryon_image(
                    prompt=user_input,
                    clothing_items=clothing_dicts,
                    user_photo_base64=user_photo_base64
                )
                
                if generation_result.get("success"):
                    image_base64 = generation_result.get("image_base64")
                    if image_base64:
                        logger.info(f"🖼️ 成功取得生成圖片，開始上傳 GCS")
                        image_bytes = base64.b64decode(image_base64)
                        generated_image_url = self._upload_image_to_gcs(image_bytes, folder="chat_outfits")
                        
                        if generated_image_url:
                            logger.info(f"✅ 圖片已上傳: {generated_image_url}")
                            response_text = f"好的，這是為您生成的穿搭建議\n📸 照片來源: {photo_source}"
                            return {
                                "type": "image",
                                "url": generated_image_url,
                                "text": response_text
                            }
                        else:
                            logger.error("GCS 上傳失敗")
                            return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
                    else:
                        logger.error("生成結果無圖片數據")
                        return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
                else:
                    logger.error(f"圖片生成失敗: {generation_result.get('error', '未知錯誤')}")
                    return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)
            
            # 一般聊天
            logger.info("💬 一般聊天請求")
            return self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)
        
        except Exception as e:
            logger.error(f"處理用戶輸入時發生錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"抱歉，處理您的請求時發生錯誤：{str(e)}"}
