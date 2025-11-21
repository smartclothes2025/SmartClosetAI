# app/services/fashion_advisor.py
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import base64
from io import BytesIO
from urllib.parse import unquote
import asyncio

# 導入 PIL Image 模組
from PIL import Image as PILImage
from PIL import Image  # 用於 download_user_photo_from_gcs

try:
    from .weather_service import weather_service
except ImportError as e:
    logging.getLogger(__name__).error(f"無法導入 WeatherService: {e}", exc_info=True)
    weather_service = None

# 檢查 GCS 是否可用
try:
    from google.cloud import storage as gcs_storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

# 載入環境變數
from dotenv import load_dotenv
import os

# 強制重新載入環境變數，覆蓋已存在的值
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path, override=True)

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationResponse

try:
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    ResourceExhausted = None

class ClothingItem: # 將 WardrobeItem 改名為 ClothingItem 以保持一致

    def __init__(self, category, name, cover_image_url):

        self.category = category
        self.name = name
        self.cover_image_url = cover_image_url

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FashionAdvisor:

    CATEGORY_MAP = {
        "tops": "tops",
        "pants": "bottoms",
        "skirts": "bottoms",
        "dresses": "tops", # 洋裝也歸類到上身來簡化處理
        "outerwear": "outerwear",
        "shoes": "shoes",
        "accessories": "accessories",
    }

    # GCS 路徑類別映射 (移除本地目錄映射)
    GCS_CATEGORY_MAP = {
        "tops": "tops",
        "bottoms": "bottoms",
        "pants": "bottoms",
        "skirts": "bottoms",
        "dresses": "dresses",
        "outerwear": "outerwear",
        "shoes": "shoes",
        "bags": "bags",
        "accessories": "accessories",
    }

    def __init__(self, **kwargs): # 為了兼容，將MAX_CLOTHING_IMAGES從參數中移除
        """初始化 FashionAdvisor，所有圖片從 GCS 讀取"""

        # --- 讀取環境變數 ---
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1") # Vertex AI 需要地區
        self.gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")  # 用於圖片生成
        
        # GCS 用戶照片 bucket
        self.user_photo_bucket_name = "smartclothes_userphoto"
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            logger.error("重大錯誤：GOOGLE_APPLICATION_CREDENTIALS 未在 .env 中設定！")
        logger.info("--- FashionAdvisor 初始化開始 (使用 Vertex AI) ---")
        # --- 初始化 Vertex AI ---
        try:
            if not self.gcp_project_id or not self.gcp_location:
                raise ValueError("GCP_PROJECT_ID 和 GCP_LOCATION 必須在 .env 中設定")
            
            # Vertex AI SDK 會自動讀取 GOOGLE_APPLICATION_CREDENTIALS
            vertexai.init(project=self.gcp_project_id, location=self.gcp_location)
            # 使用 Vertex AI 的模型名稱 (例如 "gemini-1.0-pro" 或 "gemini-3-flash-001")
            self.text_model = GenerativeModel("gemini-2.5-flash-image") 
            # 使用 Imagen 模型進行圖片生成
            # self.image_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            logger.info(f"Vertex AI (GCP) API 初始化成功")
            # logger.info(f"Imagen 圖片生成模型初始化成功")      

        except Exception as e:
            logger.error(f"Vertex AI (GCP) API 初始化失敗: {e}", exc_info=True)
            self.image_model = None
            self.text_model = None

        # --- 初始化 Google Cloud Storage (這部分不變) ---
        if self.gcs_bucket_name and self.gcp_project_id:
            try:
                self.gcs_client = storage.Client(project=self.gcp_project_id)
                self.gcs_bucket = self.gcs_client.bucket(self.gcs_bucket_name)
                logger.info(f"GCS 初始化成功，儲存桶: {self.gcs_bucket_name}")
            except Exception as e:
                logger.error(f"GCS 客戶端初始化失敗: {e}", exc_info=True)
                self.gcs_client = None
                self.gcs_bucket = None
        else:
            self.gcs_client = None
            self.gcs_bucket = None
            if not self.gcs_bucket_name:
                logger.error("GCS_BUCKET_NAME 未設定，GCS 上傳功能將無法使用。")
            if not self.gcp_project_id:

                logger.error("GCP_PROJECT_ID 未設定，GCS 客戶端無法初始化。")



        # 初始化 Gemini API (用於圖片生成)
        if self.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_api_key)
                self.genai = genai
                logger.info("Gemini API 配置成功 (用於圖片生成)")
            except Exception as e:
                logger.error(f"Gemini API 配置失敗: {e}")
                self.genai = None
        else:
            self.genai = None
            logger.warning("GEMINI_API_KEY 未設定，圖片生成功能將無法使用")
        
        # 初始化用戶照片 GCS bucket
        try:
            self.user_photo_bucket = self.gcs_client.bucket(self.user_photo_bucket_name)
            logger.info(f"用戶照片 GCS bucket 初始化成功: {self.user_photo_bucket_name}")
        except Exception as e:
            logger.error(f"用戶照片 GCS bucket 初始化失敗: {e}")
            self.user_photo_bucket = None

        logger.info(f"FashionAdvisor 初始化完成 (僅使用 GCS，不使用本地儲存)")


    def _get_gcs_wardrobe_data(self, user_id_prefix: str) -> List[ClothingItem]:

        """

        實時連接 Google Cloud Storage (GCS)，列出指定用戶路徑下的所有衣物圖片。

        """

        if not self.gcs_client or not self.gcs_bucket_name:

            logger.error("GCS 客戶端未初始化，無法獲取衣物數據。")

            return []

            

        # 根據您的截圖，用戶的衣物圖片路徑結構應為：

        # {GCS_BUCKET_NAME}/wardrobe/{USER_ID}/{CATEGORY}/{filename}.jpg

        prefix = f"wardrobe/{user_id_prefix}/"

        

        try:

            bucket = self.gcs_bucket

            # 列出所有在這個前綴下的檔案

            blobs = bucket.list_blobs(prefix=prefix)

            

            items = []

            for blob in blobs:

                if blob.name.endswith('/'):

                    continue

                    

                # 提取路徑中的類別和名稱

                # 假設路徑是 wardrobe/{USER_ID}/{CATEGORY}/{FILENAME}.ext

                parts = blob.name.replace(prefix, '').split('/') 

                

                if len(parts) >= 2:

                    category = parts[0]

                    filename = parts[-1]

                    name = filename.split('.')[0]

                    

                    if category in self.GCS_CATEGORY_MAP.values(): 
                        # 使用 gs:// URI 而不是 public_url
                        gcs_uri = f"gs://{self.gcs_bucket_name}/{blob.name}"

                        item = ClothingItem(

                            category=category,

                            name=f"{category} - {name}",

                            cover_image_url=gcs_uri  # 使用 gs:// URI

                        )

                        items.append(item)

                        

            logger.info(f"成功從 GCS 讀取到 {len(items)} 件真實衣物數據 (User: {user_id_prefix})。")

            return items

            

        except Exception as e:

            logger.error(f"從 GCS 讀取衣物數據失敗: {e}", exc_info=True)

            return []

    

    

    def get_wardrobe_items(self, user_id: str) -> List[ClothingItem]:

        """根據 user_id 實時從 GCS 獲取衣物清單。"""

        logger.info(f"開始為 User ID '{user_id}' 獲取衣物清單。")

        items = self._get_gcs_wardrobe_data(user_id)

        return items

    async def _download_image(self, gcs_uri: str) -> Optional[bytes]:
        """
        從 GCS URI 下載圖片
        
        Args:
            gcs_uri: GCS URI (gs://bucket/path/to/file)
        
        Returns:
            圖片的 bytes 數據，失敗返回 None
        """
        try:
            if not gcs_uri.startswith('gs://'):
                logger.error(f"無效的 GCS URI: {gcs_uri}")
                return None
            
            # 解析 GCS URI
            parts = gcs_uri.replace('gs://', '').split('/', 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else ''
            
            # 下載圖片
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            image_bytes = blob.download_as_bytes()
            
            return image_bytes
            
        except Exception as e:
            logger.error(f"從 GCS 下載圖片失敗 {gcs_uri}: {e}")
            return None

    async def generate_tryon_image(
        self,
        prompt: str,
        clothing_items: List[Dict[str, Any]],
        user_photo_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        使用 Gemini 2.0 Flash Experimental 的 Image Editing 功能
        直接在用戶照片上"穿"衣物，保持臉部和身材不變（複製貼上效果）
        
        Args:
            prompt: 用戶輸入的穿搭需求
            clothing_items: 衣物列表 [{"name": "...", "category": "...", "img": "url"}]
            user_photo_base64: 用戶照片的 base64 編碼（必須）
        
        Returns:
            {"success": True/False, "image_base64": "...", "error": "..."}
        """
        if not self.genai:
            return {"success": False, "error": "Gemini API 未初始化"}
        
        try:
            logger.info(f"🎨 開始生成穿搭圖片，衣物數量: {len(clothing_items)}")
            
            # 準備圖片部分
            image_parts = []
            
            # 1. 添加用戶照片（如果有）
            if user_photo_base64:
                logger.info("📸 使用用戶照片")
                image_parts.append({
                    "mime_type": "image/png",
                    "data": user_photo_base64
                })
            
            # 2. 從 GCS 下載並添加衣物圖片
            for item in clothing_items:  
                try:
                    img_url = item.get("img", "")
                    if not img_url:
                        logger.debug(f"跳過無圖片的衣物: {item.get('name')}")
                        continue
                    
                    # 支援兩種格式：gs:// 和 https://storage.googleapis.com/
                    bucket_name = None
                    blob_path = None
                    
                    if img_url.startswith("gs://"):
                        # gs://bucket_name/path/to/file.png
                        parts = img_url.replace("gs://", "").split("/", 1)
                        bucket_name = parts[0]
                        blob_path = parts[1] if len(parts) > 1 else ""
                    elif img_url.startswith("https://storage.googleapis.com/"):
                        # https://storage.googleapis.com/bucket_name/path/to/file.png
                        parts = img_url.replace("https://storage.googleapis.com/", "").split("/", 1)
                        bucket_name = parts[0]
                        blob_path = parts[1] if len(parts) > 1 else ""
                    else:
                        logger.warning(f"不支援的圖片 URL 格式: {img_url}")
                        continue
                    
                    if not bucket_name or not blob_path:
                        logger.warning(f"無法解析圖片 URL: {img_url}")
                        continue
                    
                    # 從 GCS 下載圖片
                    logger.info(f"📥 下載衣物圖片: {item.get('name')} from gs://{bucket_name}/{blob_path}")
                    bucket = self.gcs_client.bucket(bucket_name)
                    blob = bucket.blob(blob_path)
                    
                    # 檢查檔案是否存在
                    if not blob.exists():
                        logger.warning(f"⚠️ 圖片不存在: gs://{bucket_name}/{blob_path}")
                        continue
                    
                    image_bytes = blob.download_as_bytes()
                    
                    # 轉換為 base64
                    img_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    
                    image_parts.append({
                        "mime_type": "image/png",  # 根據實際格式
                        "data": img_base64
                    })
                    logger.info(f"✅ 已載入衣物: {item.get('name')} ({len(image_bytes)} bytes)")
                    
                except Exception as e:
                    logger.error(f"❌ 載入衣物圖片失敗 {item.get('name')}: {e}", exc_info=True)
                    continue
            
            if not image_parts:
                return {"success": False, "error": "沒有可用的圖片"}
            
            # 3. 檢查是否有用戶照片（必須）
            if not user_photo_base64:
                return {"success": False, "error": "需要用戶照片才能進行虛擬試穿"}
            
            logger.info("🎨 使用 Gemini 2.5 Flash Image 生成虛擬試穿圖片（必定返回圖片）...")
            logger.info(f"📸 將基於用戶照片生成穿搭效果，成功載入的衣物數量: {len(image_parts)}")
            
            # 構建衣物描述（用於放入提示詞）
            clothing_details = []
            item_index = 2 # 從 Image #2 開始算衣物

            clothing_items_with_img = [item for item in clothing_items if item.get("img")]
            fallback_clothing_names = [item.get("name", "未命名") for item in clothing_items_with_img]
            
            for item in clothing_items_with_img:
                clothing_details.append(f"Images #{item_index}: {item.get('name', '未命名')} ({item.get('category', '未分類')})")
                item_index += 1
            
            clothing_description = "\n".join(clothing_details)
            
            logger.info("🎨 使用 Gemini 2.5 Flash Image 生成虛擬試穿圖片...")
            
            
            # 構建詳細提示詞
            generation_prompt = f"""🎯 CRITICAL TASK: Generate a **Photo-Realistic Virtual Try-On** with **ABSOLUTE IDENTITY CLONING**.

📸 **REFERENCE IMAGE (Image #1)**: This is the USER'S ACTUAL PHOTO. This image dictates the *ONLY* person allowed in the final output.

**INPUT REFERENCES:**
- **Image #1 (The User):** This is the person whose **EXACT FACE, IDENTITY, HAIR, and SKIN TONE** must be preserved. Do not change their appearance, age, or gender. This is the **BASE IMAGE** for the edit.
- **Clothing Items:**
{clothing_description}

**REQUIRED OUTPUT:**
Generate a new, single, photorealistic image that looks like a high-quality, professional **studio try-on photo**.

1. **FACE AND IDENTITY PRESERVATION 🔴 ABSOLUTE PRIORITY**:
   - The person in the generated image **MUST be an IDENTICAL CLONE** of the person in Image #1.
   - **COPY EXACTLY**: Their face shape, eyes, nose, mouth, eyebrows, skin tone, hair color, and hairstyle.
   - **DO NOT** beautify, smooth, stylize, or model the face. The result must look like the user, **NOT** a model.
   - **PRIORITIZE FACE MATCHING ABOVE ALL OTHER FACTORS. (If face quality conflicts with clothing quality, prioritize the face.)**

2. **CLOTHING REQUIREMENTS**:
   - The person MUST wear clothes that look **IDENTICAL** to the provided product images.
   - The fabric must show **realistic folds and shadows**, accurately blending with the body shape.
   - **STYLE**: Match the **professional eCommerce studio style** (clean and focused on the garment).

3. **VISUAL PRESENTATION (Studio Style)**:
   - **REALISM & CLARITY**: The final output must be a high-detail, realistic photo.
   - **BACKGROUND**: **Simple, clean, professional studio background (e.g., pure grey, light beige, or white). AVOID COMPLEX SCENES, STREETS, OR OUTDOORS.**
   - **POSE**: Natural standing pose, clear and straight-on.

4. **USER'S ADDITIONAL REQUEST**: {prompt}

🎯 **TASK SUMMARY**: Generate a **studio-quality** image of the **EXACT SAME PERSON** from Image #1 wearing the exact clothes from the subsequent images. **DO NOT output ANY text part.**
"""
            
            logger.info(f"🎨 Gemini 2.5 Flash Image 提示詞: {generation_prompt[:150]}...")
            
            # 使用 Gemini 2.5 Flash Image 生成
            model = GenerativeModel('gemini-2.5-flash-image')
            
            # 準備內容：提示詞 + 用戶照片 + 衣物圖片
            contents = [generation_prompt]
            
            
            contents.append(Part.from_data(
                data=base64.b64decode(image_parts[0]['data']),
                mime_type=image_parts[0]['mime_type']
            ))
            
            for img_part in image_parts[1:]:
                contents.append(Part.from_data(
                    data=base64.b64decode(img_part['data']),
                    mime_type=img_part['mime_type']
                ))
            
            # 調用 Gemini 生成
            response = model.generate_content(contents)

            # # --- 新增的診斷日誌提取 ---
            # diagnosis_parts = []
            # if response and hasattr(response, 'candidates'):
            #     for candidate in response.candidates:
            #         if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
            #             for part in candidate.content.parts:
            #                 if hasattr(part, 'text'):
            #                     diagnosis_parts.append(part.text.strip())

            # if diagnosis_parts:
            #     full_diagnosis = "\n---\n".join(diagnosis_parts)
            #     logger.warning("💡 模型自我診斷報告 (完整輸出)：\n%s", full_diagnosis)
           
            
            # 處理響應 - 檢查是否有圖片
            if response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            # 檢查是否有圖片數據
                            if hasattr(part, 'inline_data') and part.inline_data:
                                image_data = part.inline_data.data
                                image_base64 = base64.b64encode(image_data).decode('utf-8')
                                
                                logger.info("✅ Gemini 2.5 Flash Image 虛擬試穿圖片生成成功！")
                                return {
                                    "success": True,
                                    "image_base64": image_base64
                                }
            
            # 如果 Gemini 返回文字而非圖片
            if response and hasattr(response, 'text') and response.text:
                logger.warning(f"⚠️ Gemini 返回文字而非圖片: {response.text[:200]}")
            
            # 如果還是失敗，生成一張預設圖片
            logger.error("❌ Gemini 未返回圖片，生成預設圖片")
            
            # 創建一張簡單的預設圖片
            from PIL import Image as PILImage, ImageDraw, ImageFont
            
            default_img = PILImage.new('RGB', (512, 768), color=(240, 240, 240))
            draw = ImageDraw.Draw(default_img)
            
            # 繪製文字
            fallback_preview = fallback_clothing_names[:5] if fallback_clothing_names else ["(無可用衣物)"]
            text = "Virtual Try-On\n\nClothing Items:\n" + "\n".join(fallback_preview)
            draw.text((50, 200), text, fill=(100, 100, 100))
            
            # 轉換為 base64
            img_byte_arr = BytesIO()
            default_img.save(img_byte_arr, format='PNG')
            image_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            logger.info("✅ 已生成預設圖片")
            return {
                "success": True,
                "image_base64": image_base64
            }
            
        except Exception as e:
            logger.error(f"❌ 生成穿搭圖片失敗: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def is_outfit_request(self, user_input: str) -> bool:
        """簡單判斷使用者是否在詢問穿搭"""
        keywords = ["穿", "穿搭", "衣服", "搭配", "服裝", "試穿", "推薦"]
        is_request = any(word in user_input for word in keywords)
        logger.debug(f"判斷 '{user_input}' 是否為穿搭請求: {is_request}")
        return is_request


    def _upload_image_to_gcs(self, image_data: bytes, folder: str = "generated_outfits") -> Optional[str]:
        """
        將圖片數據上傳到 GCS 並返回公共 URL。
        """
        if not self.gcs_bucket:
            logger.error("GCS 儲存桶未初始化，無法上傳圖片。")
            return None
        filename = f"{folder}/{datetime.now().strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}.png"
        blob = self.gcs_bucket.blob(filename)
        try:
            blob.upload_from_string(image_data, content_type="image/png")
            # 設置公共讀取權限 (如果儲存桶沒有統一公共訪問權限)
            # blob.make_public() # 如果儲存桶已經允許 allUsers, 這行可以省略
            public_url = blob.public_url
            logger.info(f"圖片成功上傳到 GCS: {public_url}")
            return public_url
        except Exception as e:
            logger.error(f"上傳圖片到 GCS 失敗: {e}", exc_info=True)
            return None


    def chat_with_gemini(self, user_input: str, wardrobe_items: List[ClothingItem], weather_info: Optional[Dict[str, Any]] = None, weather_advice: str = "") -> Dict[str, Any]:
        """
        使用 Gemini 模型進行一般聊天，並整合衣櫃清單和天氣資訊。
        """
        logger.info("進行一般聊天模式 (Gemini)。")
        if not self.text_model:
            logger.error("Gemini 文本模型未初始化，無法執行聊天功能。")
            return {"type": "text", "text": "錯誤：聊天服務未正確設定。請檢查服務器的 Vertex AI/GCP 設定。"}
        try:

            # 使用傳入的 wardrobe_items，不需要再次調用 get_wardrobe_items
            # 將 wardrobe_items 轉換為易於閱讀的描述
            wardrobe_summary = ", ".join([f"{item.category}: {item.name}" for item in wardrobe_items]) if wardrobe_items else "衣櫃目前是空的"

            # 整合天氣資訊到 prompt
            weather_context = ""
            if weather_info:
                weather_context = f"""


當前天氣資訊：
- 地點：{weather_info['city']}
- 溫度：{weather_info['temperature']}°C（體感溫度：{weather_info['feels_like']}°C）
- 天氣狀況：{weather_info['weather_description']}
- 濕度：{weather_info['humidity']}%
- 風速：{weather_info['wind_speed']} m/s
天氣穿搭建議：{weather_advice}
"""
            # 將系統指令和用戶輸入整合到 prompt 中
            full_prompt = f"""你是一個智慧穿搭助手，請根據使用者的問題、他們現有的衣櫃清單和當前天氣狀況提供專業建議。
如果使用者是詢問穿搭建議，請盡可能在文字上給出包含他們現有衣物的搭配方案，並考慮當前天氣狀況，即使圖片生成失敗也一樣。
使用者的衣櫃清單: {wardrobe_summary}{weather_context}
使用者說：'{user_input}'"""


            # 直接調用 generate_content，不使用 config 參數

            response: GenerationResponse = self.text_model.generate_content(full_prompt)

                        

            # 檢查是否有候選回應以及內容

            if not response.candidates or not response.candidates[0].content.parts:
                logger.warning("Gemini 模型回傳空的候選內容。")
                return {"type": "text", "text": "抱歉，我暫時無法回答這個問題。"}
            gemini_text = response.candidates[0].content.parts[0].text.strip()
            if not gemini_text:
                logger.warning("Gemini 聊天模型回傳空字串。")
                return {"type": "text", "text": "抱歉，我暫時無法回答這個問題。"}

            logger.info(f"Gemini 聊天回應: {gemini_text[:100]}...")
            return {"type": "text", "text": gemini_text}
        except Exception as e:
            if ResourceExhausted and isinstance(e, ResourceExhausted):
                logger.error(f"與 Gemini 聊天時發生 ResourceExhausted 錯誤: {str(e)}", exc_info=True)
                return {
                    "type": "text",
                    "text": "目前生成服務臨時忙碌（429 Resource exhausted），請稍後再試或稍微減少請求頻率。"
                }
            logger.error(f"與 Gemini 聊天時發生錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}



    
        
    def _get_selected_clothing_items(self, user_id: str, selected_items: List[dict]) -> List[ClothingItem]:
        """
        根據前端傳入的精確 ID，從 GCS 檢查並獲取衣物的完整對象（包含 GCS URL）。
        """
        all_wardrobe_items = self.get_wardrobe_items(user_id) # 獲取所有衣物
        selected_ids = {item.id for item in selected_items} # 假設前端傳入的 item 有 id 欄位


        final_items = []
        for item_in in selected_items:
            # 找到與 item_in 匹配的 GCS 上的真實衣物對象 (通常透過 ID)
            matching_item = next((item for item in all_wardrobe_items if item.name == item_in.name and item.category == item_in.category), None)

            if matching_item:
                 final_items.append(matching_item)
            else:
                 # 如果找不到 GCS URL，至少保留其文字資訊，供 Gemini 參考
                 final_items.append(ClothingItem(
                     category=item_in.category,
                     name=item_in.name,
                     cover_image_url=None # 無圖片 URL
                 ))
        return final_items

    async def process_fitting_request(self, user_id: str, user_input: str, selected_items: List[dict]) -> Dict[str, Any]:
        """
        專門用於虛擬試衣頁面，根據精確選擇的衣物生成圖片。
        """
        logger.info(f"處理虛擬試衣生成請求：User ID: {user_id}, Items: {len(selected_items)}")

        # 1. 獲取選中衣物的完整資訊 (含 GCS URL)
        wardrobe_items = self._get_selected_clothing_items(user_id, selected_items)
        if not wardrobe_items:
            return {"type": "text", "text": "請先在衣櫃中選擇至少一件衣物。"}
        # 轉換 ClothingItem 列表為 Dict 列表
        clothing_dicts = [
            {"name": item.name, "category": item.category, "img": item.cover_image_url}
            for item in wardrobe_items if item.cover_image_url
        ]

        if not clothing_dicts:
             return {"type": "text", "text": "所選衣物均無有效的圖片URL，無法進行虛擬試穿。"}

        # 2. 呼叫核心的圖片生成邏輯 (多圖融合)

        generation_result = await self.generate_tryon_image(
            prompt=user_input, 
            clothing_items=clothing_dicts,
            user_photo_base64=None # 虛擬試衣頁面通常沒有用戶頭貼
        )
        # 3. 處理結果
        if generation_result.get("success"):
            image_base64 = generation_result.get("image_base64")
            if image_base64:
                image_bytes = base64.b64decode(image_base64)
                generated_image_url = self._upload_image_to_gcs(image_bytes, folder="virtual_fitting_page")
            else:
                generated_image_url = None

            if generated_image_url:
                return {
                    "type": "image",
                    "url": generated_image_url,
                    "text": f"好的，這是根據您選中的 {len(clothing_dicts)} 件衣物生成的虛擬試穿結果："
                }

            else:
                logger.error("虛擬試穿成功但 GCS 上傳失敗，轉為純文字。")
                return self.chat_with_gemini(user_input, wardrobe_items)

        else:
            # 如果圖片生成失敗，退回純文字建議
            logger.error(f"虛擬試穿生成失敗: {generation_result.get('error', '未知錯誤')}")
            chat_response = self.chat_with_gemini(user_input, wardrobe_items)

            # 在文字回應前加上錯誤提示
            error_text = f"⚠️ 虛擬試穿圖片生成失敗（{generation_result.get('error', '未知錯誤')}）。我將提供文字建議代替。\n\n"
            chat_response["text"] = error_text + chat_response.get("text", "")

            return chat_response


    async def download_user_photo_from_gcs(
        self,
        picture_uri: str,
        user_id: str
    ) -> Optional[str]:
        """
        從 GCS 下載用戶頭貼並轉換為 base64
        
        Args:
            picture_uri: 用戶頭貼的 GCS URI 或完整路徑
            user_id: 用戶 ID
            
        Returns:
            Optional[str]: base64 編碼的圖片，如果失敗則返回 None
        """
        try:
            # 檢查 GCS 是否可用
            if not GCS_AVAILABLE:
                logger.warning("google-cloud-storage 未安裝，無法下載用戶頭貼")
                return None
            
            # 構建完整的 GCS URI
            # 如果 picture_uri 已經是完整的 gs:// 格式，直接使用
            # 否則假設它是相對路徑，需要加上 bucket 和路徑前綴
            if picture_uri.startswith('gs://'):
                gcs_uri = picture_uri
            else:
                # 假設格式為 smartclothes_userphoto/{user_id}/filename
                # 或者只是 filename，需要構建完整路徑
                bucket_name = "smartclothes_userphoto"
                
                # 如果 picture_uri 不包含用戶 ID 路徑，加上它
                if not picture_uri.startswith(f"{user_id}/"):
                    blob_path = f"{user_id}/{picture_uri}"
                else:
                    blob_path = picture_uri
                gcs_uri = f"gs://{bucket_name}/{blob_path}"
            
            logger.info(f"📥 正在從 GCS 下載用戶頭貼: {gcs_uri}")
            # 🔥 關鍵修改：直接下載並返回 base64，不要重新處理
            # 解析 GCS URI
            parts = gcs_uri.replace('gs://', '').split('/', 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else ''
            
            # 下載圖片
            bucket = self.gcs_client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            if not blob.exists():
                logger.warning(f"GCS 檔案不存在: {gcs_uri}")
                return None
        
            img_data = blob.download_as_bytes()
        
            if not img_data or len(img_data) < 100:
                logger.warning(f"下載的圖片數據太小或為空: {len(img_data) if img_data else 0} bytes")
                return None

            # 🔥 只做基本驗證，確認是有效圖片
            try:
                img = Image.open(BytesIO(img_data))
                logger.info(f"✅ 圖片驗證通過 - 格式: {img.format}, 尺寸: {img.size}, 模式: {img.mode}")
            except Exception as img_error:
                logger.error(f"無法解析下載的圖片: {str(img_error)}")
                return None
            
            # 🔥 直接返回原始圖片的 base64，不做任何轉換
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            
            logger.info(f"✅ 成功下載並轉換用戶頭貼 (原始大小: {len(img_data) / 1024:.1f} KB)")
            return img_base64
        
        except Exception as e:
            logger.error(f"下載用戶頭貼時發生錯誤: {str(e)}", exc_info=True)
            return None
            
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
                {"mime_type": "image/png", "data": img_bytes}
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



    async def process_user_input(self, user_id: str, user_input: str, user_image_data: Optional[str] = None, user_picture_uri: Optional[str] = None, city: str = "Taoyuan", country_code: str = "TW") -> Dict[str, Any]:
        """
        處理使用者輸入，如果偵測到穿搭請求，則嘗試生成圖片；否則進行一般聊天。
        實現：1. 根據用戶圖片進行虛擬試穿 2. 根據上傳圖片進行虛擬試穿 3. 整合天氣資訊提供穿搭建議
        """
        logger.info(f"開始處理User '{user_id}'的輸入: '{user_input}'，是否有使用者圖片: {bool(user_image_data)}")
        # 獲取天氣資訊
        weather_info = None
        weather_advice = ""
        if weather_service:
            try:
                weather_info = await weather_service.get_weather_by_city(city, country_code)
                if weather_info:
                    weather_advice = weather_service.get_weather_based_clothing_advice(weather_info)
                    logger.info(f"🌤️ 天氣資訊已獲取：{weather_info['city']} {weather_info['temperature']}°C {weather_info['weather_description']}")
            except Exception as e:
                logger.warning(f"獲取天氣資訊失敗: {str(e)}")

        if not self.genai:
             logger.critical("Gemini API 未初始化。")
             return {"type": "text", "text": "嚴重錯誤：圖片生成服務未啟動。"}

        wardrobe_items = self.get_wardrobe_items(user_id)


        # 照片優先級：1. 前端上傳 2. 用戶頭貼 3. 無照片
        user_photo_base64 = user_image_data
        photo_source = "上傳照片" if user_image_data else None
        logger.info("📸 照片狀態檢查:")
        logger.info(f"   - 前端上傳照片: {'有' if user_image_data else '無'} (長度: {len(user_image_data) if user_image_data else 0} chars)")
        logger.info(f"   - 用戶頭貼 URI: {user_picture_uri if user_picture_uri else '無'}")

        if not user_photo_base64 and user_picture_uri:
            logger.info(f"🔄 開始下載用戶頭貼: {user_picture_uri}")
            try:
                user_photo_base64 = await self.download_user_photo_from_gcs(
                    picture_uri=user_picture_uri,
                    user_id=user_id
                )

                if user_photo_base64:
                    # user_photo_data_bytes = base64.b64decode(user_photo_base64)
                    # cropped_face_base64 = self._crop_and_enhance_face(user_photo_data_bytes)

                    # if cropped_face_base64:
                    #     user_photo_base64 = cropped_face_base64
                    #     logger.info(f"✅ 已使用處理後的臉部照片替換原始照片進行克隆，base64 長度: {len(user_photo_base64)} characters")
                    # else:
                    #     logger.warning("⚠️ 臉部處理失敗，使用原始照片。")
                    logger.info(f"✅ 使用完整的原始照片進行 Image-to-Image 克隆，base64 長度: {len(user_photo_base64)} characters")
                    
                    photo_source = "用戶頭貼"
                else:
                    logger.warning("⚠️ 用戶頭貼下載返回 None")
            except Exception as download_error:
                logger.error(f"❌ 用戶頭貼下載失敗: {str(download_error)}", exc_info=True)
        
        if not photo_source:
            photo_source = "預設模特兒"
            logger.warning("⚠️ 沒有可用的用戶照片，將使用預設模特兒")
        
        logger.info(f"📸 最終照片來源: {photo_source}")
        logger.info(f"📸 user_photo_base64 是否存在: {'是' if user_photo_base64 else '否'}")
        if user_photo_base64:
            logger.info(f"📊 user_photo_base64 截斷預覽: {user_photo_base64[:40]}...")



        try:
            if self.is_outfit_request(user_input) and wardrobe_items:
                logger.info("👗 偵測到穿搭請求，執行虛擬試穿。")

            

                # 轉換 ClothingItem 列表為 Dict 列表
                clothing_dicts = [
                    {"name": item.name, "category": item.category, "img": item.cover_image_url}
                    for item in wardrobe_items if item.cover_image_url
                ]
                logger.info(f"🧾 從衣櫃整理出 {len(clothing_dicts)} 件含圖片的衣物資料。")

                if not clothing_dicts:
                     logger.warning("衣櫃圖片 URL 皆為空，無法進行圖片生成，轉為文字建議。")
                     return self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)

                # 💡 呼叫自己的圖片生成方法 (使用所有衣物)

                logger.info(f"🛠️ 準備呼叫 generate_tryon_image()，照片來源: {photo_source}，是否具備照片: {'是' if user_photo_base64 else '否'}")

                generation_result = await self.generate_tryon_image(
                    prompt=user_input,
                    clothing_items=clothing_dicts,
                    user_photo_base64=user_photo_base64 # 傳入用戶圖片/頭貼
                )

                
                if generation_result.get("success"):
                    image_base64 = generation_result.get("image_base64")
                    if image_base64:
                        logger.info(f"🖼️ 成功取得生成圖片，長度: {len(image_base64)} characters，開始上傳 GCS。")
                        image_bytes = base64.b64decode(image_base64)
                        # 將生成的圖片 (base64) 上傳到 GCS 
                        generated_image_url = self._upload_image_to_gcs(image_bytes, folder="virtual_tryon_outfits_chat")
                    else:
                        generated_image_url = None

                    if generated_image_url:
                        logger.info(f"影像已生成並上傳，URL: {generated_image_url}")
                        return {
                            "type": "image",
                            "url": generated_image_url,
                            "text": f"好的，這是為您生成的穿搭建議\n📸 照片來源: {photo_source}"
                        }
                    else:
                        # GCS 上傳失敗，回退到文字
                        logger.error("虛擬試穿成功但 GCS 上傳失敗，轉為一般聊天。")
                        return self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)
                else:
                    logger.error(f"虛擬試穿失敗: {generation_result.get('error', '未知錯誤')}，轉為一般聊天。")
                    # 影像生成失敗，直接呼叫 Gemini 聊天
                    chat_response = self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)
                    # 在文字回應前加上錯誤提示
                    error_text = f"⚠️ 虛擬穿搭圖片生成失敗（{generation_result.get('error', '未知錯誤')}）。我將提供文字建議代替。\n\n"
                    chat_response["text"] = error_text + chat_response.get("text", "")
                    return chat_response
            # 如果非穿搭需求或衣櫃為空，進行一般聊天
            return self.chat_with_gemini(user_input, wardrobe_items, weather_info, weather_advice)
        except Exception as e:
            logger.error(f"FashionAdvisor 處理錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}




# Singleton instance
image_service = FashionAdvisor()