# app/services/image_generation.py
"""
Image Generation Service
Uses Google Gemini and Imagen for virtual try-on
"""
import os
import base64
import requests
from typing import Optional, Dict, Any, List
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from google.cloud import aiplatform
from google.oauth2 import service_account
import logging
import asyncio
import time

logger = logging.getLogger(__name__)

# 嘗試導入 GCS 客戶端
try:
    from google.cloud import storage as gcs_storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("google-cloud-storage 未安裝，無法直接從 GCS 下載圖片")


class ImageGenerationService:
    """
    Service for generating realistic try-on images using Google Gemini and Imagen
    """
    
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
        
        # Initialize Vertex AI for Imagen
        if self.gcp_project_id:
            try:
                aiplatform.init(project=self.gcp_project_id, location=self.gcp_location)
            except Exception as e:
                print(f"Vertex AI initialization warning: {e}")
    
    async def generate_tryon_image(
        self, 
        prompt: str, 
        style: str = "realistic",
        width: int = 768,
        height: int = 1024,
        clothing_items: Optional[List[Dict]] = None,
        user_photo_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate try-on image using Google Gemini Image-to-Image
        只支援使用實際衣物圖片進行虛擬試穿 (Image-to-Image)
        
        Args:
            prompt: 用戶輸入的提示詞
            style: 風格（目前未使用）
            width: 寬度（目前未使用）
            height: 高度（目前未使用）
            clothing_items: 衣物列表（包含圖片 URL）
            user_photo_base64: 可選的用戶照片（base64 編碼）
        """
        
        # 檢查是否提供衣物圖片
        if not clothing_items:
            logger.error("❌ 未提供衣物圖片，無法進行虛擬試穿")
            return {
                "success": False,
                "error": "虛擬試衣需要提供衣物圖片。請選擇至少一件有圖片的衣物。",
                "prompt": prompt
            }
        
        # 檢查 API Key
        if not self.gemini_api_key:
            logger.error("❌ 未配置 GEMINI_API_KEY")
            return {
                "success": False,
                "error": "請配置 GEMINI_API_KEY 來使用虛擬試衣功能",
                "prompt": prompt
            }
        
        # 使用 Gemini 2.5 Flash Image 進行 Image-to-Image 生成
        try:
            result = await self._generate_with_clothing_images(prompt, clothing_items, user_photo_base64)
            if result and result.get("success"):
                return result
            else:
                # 如果生成失敗，返回錯誤
                error_msg = result.get("error", "圖片生成失敗") if result else "圖片生成失敗"
                logger.error(f"❌ 虛擬試穿失敗: {error_msg}")
                return {
                    "success": False,
                    "error": f"虛擬試穿生成失敗: {error_msg}",
                    "prompt": prompt
                }
        except Exception as e:
            logger.error(f"❌ Gemini Image-to-Image 生成錯誤: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"虛擬試穿生成錯誤: {str(e)}",
                "prompt": prompt
            }
    
    def _download_image(self, img_url: str) -> bytes:
        """
        下載圖片，支援 HTTP URL 和 GCS URI
        
        Args:
            img_url: 圖片 URL (http://... 或 gs://...)
            
        Returns:
            bytes: 圖片二進制數據
        """
        if img_url.startswith('gs://'):
            # GCS URI: gs://bucket_name/path/to/file
            if not GCS_AVAILABLE:
                raise Exception("google-cloud-storage 未安裝，無法從 GCS 下載")
            
            # 解析 GCS URI
            parts = img_url[5:].split('/', 1)  # 移除 'gs://' 並分割
            if len(parts) != 2:
                raise Exception(f"無效的 GCS URI 格式: {img_url}")
            
            bucket_name, blob_name = parts
            logger.info(f"   從 GCS 下載: bucket={bucket_name}, blob={blob_name}")
            
            # 下載 from GCS
            client = gcs_storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            if not blob.exists():
                raise Exception(f"GCS 檔案不存在: {img_url}")
            
            img_data = blob.download_as_bytes()
            logger.info(f"   GCS 下載成功: {len(img_data)} bytes")
            return img_data
            
        elif img_url.startswith(('http://', 'https://')):
            # HTTP URL
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(img_url, timeout=15, headers=headers, allow_redirects=True)
            
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                if response.status_code == 403:
                    error_msg += " - 訪問被拒絕"
                elif response.status_code == 404:
                    error_msg += " - 圖片不存在"
                raise Exception(error_msg)
            
            return response.content
        else:
            raise Exception(f"不支援的 URL 格式: {img_url}")
    
    async def _generate_with_clothing_images(self, prompt: str, clothing_items: List[Dict], user_photo_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Use Gemini 2.5 Flash Image with actual clothing images for virtual try-on
        使用實際衣物圖片進行虛擬試穿
        
        Args:
            prompt: 用戶輸入的提示詞
            clothing_items: 衣物列表（包含圖片 URL）
            user_photo_base64: 可選的用戶臉部照片（base64 編碼）
        """
        try:
            model = genai.GenerativeModel('gemini-2.5-flash-image')
            
            # Prepare content parts: text prompt + clothing images
            content_parts = []
            
            # 按類別組織衣物,以便生成更精確的描述
            categorized_items = {
                'tops': [],
                'bottoms': [],
                'dresses': [],
                'outerwear': [],
                'shoes': [],
                'accessories': []
            }
            
            category_map = {
                '上衣': 'tops',
                'tops': 'tops',
                '外套': 'outerwear',
                'outerwear': 'outerwear',
                '褲子': 'bottoms',
                'bottoms': 'bottoms',
                'pants': 'bottoms',
                '裙子': 'bottoms',
                'skirts': 'bottoms',
                'skirt': 'bottoms',
                '洋裝': 'dresses',
                'dresses': 'dresses',
                'dress': 'dresses',
                '鞋子': 'shoes',
                'shoes': 'shoes',
                '配件': 'accessories',
                'accessories': 'accessories'
            }
            
            for item in clothing_items:
                category = item.get('category', '').lower()
                mapped_category = category_map.get(category, 'accessories')
                categorized_items[mapped_category].append(item)
            
            # 構建詳細的衣物描述
            clothing_details = []
            item_index = 1
            
            for category, items in categorized_items.items():
                if items:
                    for item in items:
                        clothing_details.append(f"第{item_index}張圖片: {item.get('name', '未命名')} ({category})")
                        item_index += 1
            
            clothing_description = "\n".join(clothing_details)
            
            # 根據是否有用戶照片，調整提示詞
            if user_photo_base64:
                # 有用戶照片：要求使用用戶的臉部特徵
                tryon_prompt = f"""🎯 CRITICAL TASK: Virtual Try-On with User's Exact Facial Features

📸 **REFERENCE IMAGE (Image #1)**: This is the USER'S ACTUAL PHOTO. You MUST preserve their exact appearance.

⚠️ **MOST IMPORTANT RULES** (FAILURE TO FOLLOW = TASK FAILED):

1. **PRESERVE USER'S IDENTITY** 🔴 CRITICAL:
   - The person in the generated image MUST look EXACTLY like the person in Image #1
   - COPY their facial features: face shape, eyes, nose, mouth, eyebrows, skin tone
   - COPY their gender, age appearance, and overall look
   - COPY their hair color and hairstyle
   - DO NOT change their ethnicity, gender, or any facial characteristics
   - This is NOT about creating a "similar" person - it's about showing THE SAME PERSON wearing different clothes

2. **GENDER ACCURACY** 🔴 CRITICAL:
   - If Image #1 shows a MALE person → Generate a MALE person
   - If Image #1 shows a FEMALE person → Generate a FEMALE person
   - DO NOT change the person's gender under any circumstances

3. **CLOTHING ITEMS** (Images #2 onwards):
{clothing_description}

4. **CLOTHING REQUIREMENTS**:
   - Study each clothing image carefully (color, pattern, texture, cut)
   - The person MUST wear clothes that look EXACTLY like these images
   - DO NOT create new designs or change colors/patterns
   - DO NOT merge multiple items into one piece

5. **OUTFIT COMPOSITION**:
   - Tops → upper body
   - Bottoms (pants/skirts) → lower body
   - Dresses → single piece outfit
   - Outerwear → outermost layer
   - Shoes → on feet
   - Accessories → appropriately placed

6. **VISUAL PRESENTATION**:
   - Natural, elegant pose
   - Full body shot showing all clothing details
   - Simple background (solid color or minimal scene)
   - Soft, natural lighting
   - High resolution, professional photography quality

7. **USER'S ADDITIONAL REQUEST**: {prompt}

🎯 **TASK SUMMARY**: Generate a photo of THE EXACT SAME PERSON from Image #1 wearing the exact clothes from the subsequent images. This person must be recognizable as the same individual - same face, same gender, same overall appearance.

⚠️ **VERIFICATION CHECKLIST**:
- [ ] Does the person have the same face as Image #1?
- [ ] Does the person have the same gender as Image #1?
- [ ] Are the clothes identical to the provided clothing images?

Now generate the virtual try-on image following ALL requirements above."""
            else:
                # 沒有用戶照片：使用亞洲女性模特兒
                tryon_prompt = f"""🎯 虛擬試穿任務 - 請精確執行以下指令:

📋 **衣物清單** (按順序提供的圖片):
{clothing_description}

🎨 **生成要求** (必須嚴格遵守):

1. **精確還原每件衣物**:
   - 仔細觀察每張衣物圖片的顏色、圖案、材質、剪裁
   - 在生成的圖片中,模特兒必須穿著與這些圖片**完全相同**的服裝
   - 不要創造新的服裝,不要改變顏色或圖案
   - 不要將多件衣物合併成一件(例如:不要將上衣+裙子變成連衣裙)

2. **正確的穿搭組合**:
   - 如果有上衣(tops),穿在上半身
   - 如果有褲子或裙子(bottoms),穿在下半身
   - 如果有洋裝(dress),作為單件穿著
   - 如果有外套(outerwear),穿在最外層
   - 如果有鞋子,穿在腳上
   - 如果有配件,適當搭配

3. **模特兒要求**:
   - ✅ **必須是亞洲女性（台灣）**
   - 東亞面孔特徵，自然黑髮或深棕色頭髮
   - 膚色：自然的亞洲膚色（偏白皙到自然膚色）
   - 身材：符合亞洲女性平均身材比例
   - 年齡：20-30 歲左右的年輕女性

4. **視覺呈現**:
   - 專業時尚模特兒,姿態自然優雅
   - 全身照,能清楚看到所有服裝細節
   - 簡潔的背景(純色或簡約場景)
   - 柔和自然的光線,突顯服裝質感
   - 高清晰度,專業攝影品質

5. **用戶額外需求**: {prompt}

⚠️ **重要提醒**: 請將提供的衣物圖片視為「產品照片」,您的任務是生成一張「亞洲（台灣）女性模特兒穿著這些產品的展示照片」,而不是根據風格創作新服裝。

現在請根據接下來提供的衣物圖片,生成符合以上所有要求的虛擬試穿圖片。"""
            
            content_parts.append(tryon_prompt)
            
            # 如果有用戶照片，先添加用戶照片
            if user_photo_base64:
                try:
                    logger.info("📸 檢測到用戶照片，正在處理...")
                    user_photo_data = base64.b64decode(user_photo_base64)
                    user_img = Image.open(BytesIO(user_photo_data))
                    
                    # Convert to RGB if necessary
                    if user_img.mode != 'RGB':
                        user_img = user_img.convert('RGB')
                    
                    # Resize if too large
                    max_size = 1024
                    if user_img.width > max_size or user_img.height > max_size:
                        user_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    
                    # Convert to bytes
                    user_img_byte_arr = BytesIO()
                    user_img.save(user_img_byte_arr, format='JPEG', quality=95)
                    user_img_bytes = user_img_byte_arr.getvalue()
                    
                    # Add user photo as the first image (after prompt)
                    content_parts.append({
                        "mime_type": "image/jpeg",
                        "data": user_img_bytes
                    })
                    
                    logger.info(f"✅ 用戶照片已載入 (大小: {len(user_img_bytes) / 1024:.1f} KB)")
                except Exception as e:
                    logger.warning(f"⚠️ 用戶照片處理失敗: {str(e)}，將使用預設模特兒")
            
            logger.info(f"\n{'='*60}")
            logger.info("🎯 開始虛擬試穿圖片生成")
            logger.info(f"使用用戶照片: {'是' if user_photo_base64 else '否（使用預設模特兒）'}")
            logger.info(f"衣物數量: {len(clothing_items)}")
            logger.info(f"分類統計: {[(k, len(v)) for k, v in categorized_items.items() if v]}")
            logger.info(f"{'='*60}\n")
            
            # Download and add clothing images with detailed logging
            clothing_images_loaded = 0
            failed_items = []
            
            for idx, item in enumerate(clothing_items, 1):
                img_url = item.get('img')
                item_name = item.get('name', '未命名')
                item_category = item.get('category', '未分類')
                
                if img_url:
                    try:
                        logger.info(f"📥 [{idx}/{len(clothing_items)}] 下載: {item_name} ({item_category})")
                        logger.info(f"   URL: {img_url}")
                        
                        # 下載圖片（支援 HTTP 和 GCS URI）
                        img_data = self._download_image(img_url)
                        
                        # 檢查是否為有效圖片
                        if len(img_data) < 100:
                            error_msg = f"圖片數據太小 ({len(img_data)} bytes)"
                            failed_items.append(f"{item_name}: {error_msg}")
                            logger.warning(f"   ❌ {error_msg}")
                            continue
                        
                        try:
                            img = Image.open(BytesIO(img_data))
                        except Exception as img_error:
                            error_msg = f"無法解析圖片: {str(img_error)}"
                            failed_items.append(f"{item_name}: {error_msg}")
                            logger.warning(f"   ❌ {error_msg}")
                            continue
                        
                        original_size = img.size
                        logger.info(f"   原始尺寸: {original_size[0]}x{original_size[1]}")
                        logger.info(f"   圖片模式: {img.mode}")
                        
                        # Convert to RGB if necessary
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                            logger.info(f"   已轉換為 RGB 模式")
                        
                        # Resize if too large (max 1024x1024)
                        max_size = 1024
                        if img.width > max_size or img.height > max_size:
                            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                            logger.info(f"   已調整尺寸: {img.size[0]}x{img.size[1]}")
                        
                        # Convert to bytes
                        img_byte_arr = BytesIO()
                        img.save(img_byte_arr, format='JPEG', quality=95)
                        img_bytes = img_byte_arr.getvalue()
                        
                        # Add image to content
                        content_parts.append({
                            "mime_type": "image/jpeg",
                            "data": img_bytes
                        })
                        
                        clothing_images_loaded += 1
                        logger.info(f"   ✅ 成功載入 (大小: {len(img_bytes) / 1024:.1f} KB)")
                        
                    except Exception as e:
                        error_msg = f"{type(e).__name__}: {str(e)}"
                        failed_items.append(f"{item_name}: {error_msg}")
                        logger.warning(f"   ❌ 處理失敗: {error_msg}")
                        if "GCS" in error_msg or "gs://" in str(e):
                            logger.warning(f"   提示: 請確認 GOOGLE_APPLICATION_CREDENTIALS 已正確設定")
                else:
                    failed_items.append(f"{item_name}: 無圖片 URL")
                    logger.warning(f"   ⚠️ 跳過: 無圖片 URL")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 圖片載入統計:")
            logger.info(f"   成功: {clothing_images_loaded}/{len(clothing_items)}")
            if failed_items:
                logger.warning(f"   失敗項目:")
                for failed in failed_items:
                    logger.warning(f"      - {failed}")
            logger.info(f"{'='*60}\n")
            
            if clothing_images_loaded == 0:
                logger.error("❌ 沒有成功載入任何衣物圖片,無法進行虛擬試穿")
                logger.info("🔄 將回退到純文字生成模式...")
                return {
                    "success": False,
                    "error": "No clothing images loaded",
                    "failed_items": failed_items
                }
            
            logger.info(f"🚀 開始調用 Gemini 2.5 Flash Image 模型...")
            logger.info(f"   內容部分數量: {len(content_parts)} (1 prompt + {clothing_images_loaded} images)")
            
            # Generate image with clothing images (with retry logic)
            max_retries = 3
            retry_delay = 2
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"🔄 重試第 {attempt + 1}/{max_retries} 次...")
                        await asyncio.sleep(retry_delay * attempt)
                    
                    response = model.generate_content(content_parts)
                    logger.info("✅ 模型回應已接收,正在檢查結果...")
                    break  # 成功，跳出重試循環
                    
                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    logger.warning(f"⚠️ 嘗試 {attempt + 1}/{max_retries} 失敗: {error_msg}")
                    
                    # 如果是最後一次嘗試，拋出異常
                    if attempt == max_retries - 1:
                        raise
                    
                    # 檢查是否是可重試的錯誤
                    if "RemoteDisconnected" in error_msg or "Connection" in error_msg:
                        logger.info(f"   檢測到連接錯誤，將在 {retry_delay * (attempt + 1)} 秒後重試...")
                        continue
                    else:
                        # 不可重試的錯誤，直接拋出
                        raise
            else:
                # 所有重試都失敗
                raise last_error if last_error else Exception("All retries failed")
            
            # Check if response contains image
            if response.parts:
                logger.info(f"   回應包含 {len(response.parts)} 個部分")
                for idx, part in enumerate(response.parts):
                    logger.info(f"   部分 {idx + 1}: {type(part).__name__}")
                    if hasattr(part, 'inline_data') and part.inline_data:
                        # Extract base64 image data
                        image_data = part.inline_data.data
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        
                        logger.info(f"\n{'='*60}")
                        logger.info("🎉 虛擬試穿圖片生成成功!")
                        logger.info(f"   圖片大小: {len(image_data) / 1024:.1f} KB")
                        logger.info(f"   使用衣物圖片: {clothing_images_loaded} 張")
                        logger.info(f"   生成服務: Gemini 2.5 Flash Image (多模態)")
                        logger.info(f"{'='*60}\n")
                        
                        return {
                            "success": True,
                            "image_base64": image_base64,
                            "format": "base64",
                            "prompt": prompt,
                            "service": "gemini-2.5-flash-image-with-clothing",
                            "clothing_images_used": clothing_images_loaded,
                            "method": "multimodal_with_actual_clothing_images"
                        }
                    elif hasattr(part, 'text'):
                        logger.warning(f"   ⚠️ 部分 {idx + 1} 包含文字而非圖片: {part.text[:100]}...")
            else:
                logger.warning("   ⚠️ 回應不包含任何部分")
            
            logger.error("❌ Gemini 未返回圖片數據")
            return {
                "success": False,
                "error": "Gemini did not return image data"
            }
            
        except Exception as e:
            logger.error(f"\n{'='*60}")
            logger.error(f"❌ 虛擬試穿圖片生成錯誤")
            logger.error(f"   錯誤類型: {type(e).__name__}")
            logger.error(f"   錯誤訊息: {str(e)}")
            logger.error(f"{'='*60}\n", exc_info=True)
            return {
                "success": False,
                "error": f"Gemini image generation error: {str(e)}"
            }
    
    
    
    def create_fashion_prompt(
        self,
        clothing_items: list,
        user_input: str,
        style: str = "casual"
    ) -> str:
        """
        Create optimized prompt for fashion image generation
        只需要照片，不需要身體數據
        """
        # Build clothing description
        clothing_descriptions = []
        for item in clothing_items:
            category = item.get('category', '')
            name = item.get('name', '')
            
            # Map Chinese categories to English
            category_map = {
                '上衣': 'top',
                '外套': 'jacket',
                '褲子': 'pants',
                '裙子': 'skirt',
                '洋裝': 'dress',
                '鞋子': 'shoes',
                '帽子': 'hat',
                '配件': 'accessory'
            }
            
            eng_category = category_map.get(category, category)
            clothing_descriptions.append(f"{eng_category}: {name}")
        
        clothing_text = ", ".join(clothing_descriptions)
        
        # Create comprehensive prompt (不使用身體數據，指定亞洲女性模特兒)
        prompt = f"""A professional Asian Taiwanese female fashion model wearing {clothing_text}, 
        East Asian facial features, natural black or dark brown hair,
        natural Asian skin tone, slim build typical of Asian women,
        age 20-30 years old,
        standing in a modern minimalist studio, 
        soft natural lighting, neutral background, 
        full body shot, confident and elegant pose, 
        high-end fashion photography style, 
        detailed clothing texture, realistic fabric, 
        professional fashion magazine quality"""
        
        return prompt
    
    async def enhance_with_user_photo(
        self,
        user_photo_base64: str,
        clothing_prompt: str
    ) -> Dict[str, Any]:
        """
        Analyze user photo and generate personalized try-on
        Uses Gemini Vision for analysis
        """
        if not self.gemini_api_key:
            return {
                "success": False,
                "error": "GEMINI_API_KEY not configured"
            }
        
        try:
            # Decode base64 image
            image_data = base64.b64decode(user_photo_base64)
            image = Image.open(BytesIO(image_data))
            
            # Use Gemini Vision to analyze
            model = genai.GenerativeModel('gemini-pro-vision')
            
            analysis_prompt = f"""Analyze this person's photo and describe:
            1. Body type and build
            2. Skin tone
            3. Face shape
            4. Overall style
            
            Then suggest how to best showcase these clothing items on this person:
            {clothing_prompt}
            
            Provide a detailed English prompt for AI image generation."""
            
            # Convert image for Gemini
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='JPEG')
            img_bytes = img_byte_arr.getvalue()
            
            response = model.generate_content([
                analysis_prompt,
                {"mime_type": "image/jpeg", "data": img_bytes}
            ])
            
            enhanced_prompt = response.text
            
            return {
                "success": True,
                "enhanced_prompt": enhanced_prompt,
                "analysis": response.text
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Photo analysis failed: {str(e)}"
            }


# Singleton instance
image_service = ImageGenerationService()
