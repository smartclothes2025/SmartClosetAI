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
from PIL import Image# 用於 download_user_photo_from_gcs
import httpx # 🔥 為了實現 IP-to-Geo 服務，需要導入 httpx

from .image_generation import image_service as img_gen_service
from .image_classifier import image_classifier  # 🔥 導入圖片分類服務

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
            self.image_model_name = "gemini-2.5-flash-image"
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


    def is_outfit_request(self, user_input: str) -> bool:
        """簡單判斷使用者是否在詢問穿搭"""
        keywords = [
            # 基礎穿搭詞
            "穿搭", "推薦", "搭配", "穿甚麼", "穿什麼", "怎麼穿", "穿衣", "服裝", "造型", "打扮",
            # 場景詞
            "運動", "約會", "上班", "出門", "逛街", "聚會", "派對", "面試", "旅遊", "休閒",
            # 續問/再生成
            "換一套", "再一套", "其他套", "其他的", "不喜歡", "不適合", "想改", "再看", "再來", "另一個",
            # 明確要求生圖
            "升圖", "生成圖", "生圖", "產生圖", "給我圖", "看圖", "幫我生成",
            # 英文
            "outfit", "style", "look", "wear", "OOTD"
        ]
        is_request = any(word in user_input for word in keywords)
        logger.debug(f"判斷 '{user_input}' 是否為穿搭請求: {is_request}")
        return is_request
    
    def is_weather_only_request(self, user_input: str) -> bool:
        """判斷使用者是否只在詢問天氣（不包含穿搭）"""
        weather_keywords = ["天氣", "氣溫", "溫度", "下雨", "晴天", "陰天", "weather"]
        outfit_keywords = ["穿搭", "推薦", "搭配", "穿甚麼", "穿什麼", "怎麼穿"]
        
        has_weather = any(word in user_input for word in weather_keywords)
        has_outfit = any(word in user_input for word in outfit_keywords)
        
        # 只有天氣關鍵字，沒有穿搭關鍵字
        is_weather_only = has_weather and not has_outfit
        logger.debug(f"判斷 '{user_input}' 是否只詢問天氣: {is_weather_only}")
        return is_weather_only


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


    def _generate_outfit_fallback_text(self, user_input: str, wardrobe_items: List[ClothingItem], weather_info: Optional[Dict[str, Any]] = None, weather_advice: str = "") -> Dict[str, Any]:
        """穿搭請求但圖片生成失敗時的降級文字回覆"""
        logger.info("穿搭圖片生成失敗，提供降級文字建議。")
        if wardrobe_items:
            wardrobe_summary = "、".join([f"{item.name}" for item in wardrobe_items[:5]])
            if len(wardrobe_items) > 5:
                wardrobe_summary += f" 等 {len(wardrobe_items)} 件衣物"
            
            response_text = f"""抱歉，目前無法生成穿搭圖片。

根據您的衣櫃（{wardrobe_summary}），我建議您可以嘗試以下搭配：

1. 選擇一件上衣搭配褲子或裙子
2. 根據場合選擇合適的外套
3. 搭配舒適的鞋子完成整體造型"""
            
            if weather_info:
                response_text += f"\n\n🌤️ 根據您目前所在地區的天氣（{weather_info['temperature']}°C），{weather_advice}"
            
            return {"type": "text", "text": response_text}
        else:
            return {"type": "text", "text": "您的衣櫃目前是空的，請先上傳一些衣物照片，我才能為您提供穿搭建議！"}
    
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
- 地點：您目前所在地區
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

            # 移除 Markdown 格式符號（粗體、斜體、代碼符號等）
            gemini_text = gemini_text.replace("**", "").replace("__", "").replace("*", "").replace("_", "").replace("`", "")
            
            logger.info(f"Gemini 聊天回應: {gemini_text[:100]}...")
            return {"type": "text", "text": gemini_text}
        except Exception as e:
            if ResourceExhausted and isinstance(e, ResourceExhausted):
                logger.warning(f"與 Gemini 聊天時發生 ResourceExhausted 錯誤（429），返回友善回覆: {str(e)}")
                # 返回友善的固定回覆，不顯示錯誤訊息
                return {
                    "type": "text",
                    "text": "抱歉，我無法理解你說，請再試一次！您可以問我：\n\n👗 '今天穿什麼？'\n🌤️ '今天天氣如何？'\n💡 '推薦穿搭'\n\n我會根據您的衣櫃和天氣為您提供建議！"
                }
            logger.error(f"與 Gemini 聊天時發生錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}


    
        
    def _get_selected_clothing_items(self, user_id: str, selected_items: List[dict]) -> List[ClothingItem]:
        """
        根據前端傳入的精確 ID，從 GCS 檢查並獲取衣物的完整對象（包含 GCS URL）。
        """
        all_wardrobe_items = self.get_wardrobe_items(user_id) # 獲取所有衣物
        # 假設前端傳入的 item 有 id 欄位，但此處未使用，保留原有邏輯
        # selected_ids = {item.id for item in selected_items} 

        final_items = []
        for item_in in selected_items:
            # 找到與 item_in 匹配的 GCS 上的真實衣物對象 (通常透過 ID)
            matching_item = next((item for item in all_wardrobe_items if item.name == item_in['name'] and item.category == item_in['category']), None)

            if matching_item:
                 final_items.append(matching_item)
            else:
                 # 如果找不到 GCS URL，至少保留其文字資訊，供 Gemini 參考
                 final_items.append(ClothingItem(
                     category=item_in['category'],
                     name=item_in['name'],
                     cover_image_url=None # 無圖片 URL
                 ))
        return final_items

    def _smart_select_clothing_items(self, clothing_items: List[Dict[str, Any]], max_items: int = 2) -> List[Dict[str, Any]]:
        """智能隨機挑選 2 件衣物，確保生成圖片時臉部相似度更高"""
        import random
        
        if len(clothing_items) <= max_items:
            return clothing_items
        
        items_by_category = {"tops": [], "bottoms": [], "dresses": [], "outerwear": [], "shoes": [], "accessories": [], "bags": []}
        
        for item in clothing_items:
            category = item.get("category", "").lower()
            if category in ["tops"]:
                items_by_category["tops"].append(item)
            elif category in ["bottoms", "pants", "skirts"]:
                items_by_category["bottoms"].append(item)
            elif category in ["dresses"]:
                items_by_category["dresses"].append(item)
            elif category in ["outerwear"]:
                items_by_category["outerwear"].append(item)
            elif category in ["shoes"]:
                items_by_category["shoes"].append(item)
            elif category in ["accessories"]:
                items_by_category["accessories"].append(item)
            elif category in ["bags"]:
                items_by_category["bags"].append(item)
        
        selected = []
        if items_by_category["tops"]:
            selected.append(random.choice(items_by_category["tops"]))
            if items_by_category["bottoms"] and len(selected) < max_items:
                selected.append(random.choice(items_by_category["bottoms"]))
        elif items_by_category["dresses"]:
            selected.append(random.choice(items_by_category["dresses"]))
        elif items_by_category["bottoms"]:
            selected.append(random.choice(items_by_category["bottoms"]))
        
        remaining_categories = ["outerwear", "shoes", "accessories", "bags", "tops", "bottoms", "dresses"]
        random.shuffle(remaining_categories)
        
        for cat in remaining_categories:
            if len(selected) >= max_items:
                break
            available_items = [item for item in items_by_category[cat] if item not in selected]
            if available_items:
                selected.append(random.choice(available_items))
        
        if len(selected) < 2:
            remaining = [item for item in clothing_items if item not in selected]
            random.shuffle(remaining)
            selected.extend(remaining[:max(0, 2 - len(selected))])
        
        random.shuffle(selected)
        logger.info(f"🎯 智能隨機挑選結果：")
        for idx, item in enumerate(selected, 1):
            logger.info(f"   {idx}. {item.get('name')} ({item.get('category')})")
        return selected[:max_items]

    async def process_user_input(
        self, 
        user_id: str, 
        user_input: str, 
        user_images: Optional[List[str]] = None,
        picture_uri: Optional[str] = None,
        user_gender: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        city: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        處理小助手的用戶輸入（聊天頁面）- 支援多圖片上傳
        
        Args:
            user_id: 用戶 ID
            user_input: 用戶輸入的文字
            user_images: 前端上傳的照片列表 (base64)，最多 3 張
            picture_uri: 用戶頭貼 URI
            user_gender: 用戶性別
            lat: 用戶目前座標的緯度
            lon: 用戶目前座標的經度
            city: 用戶目前所在地區的城市名稱
        """
        logger.info(f"🤖 小助手處理請求：User ID: {user_id}")
        logger.info(f"   輸入: {user_input}")
        logger.info(f"   上傳圖片數量: {len(user_images) if user_images else 0}")
        
        # 1. 獲取天氣資訊（優先使用使用者目前座標）
        weather_info = None
        weather_advice = ""
        try:
            if weather_service:
                if lat is not None and lon is not None:
                    weather_info = await weather_service.get_weather_by_coordinates(lat=lat, lon=lon)
                else:
                    city_arg = city or "Taoyuan"
                    weather_info = await weather_service.get_weather_info(city=city_arg)

                if weather_info:
                    if "suggestion" not in weather_info:
                        weather_info["suggestion"] = weather_service.get_weather_based_clothing_advice(weather_info)
                    temp = weather_info.get("temperature", 20)
                    weather_advice = weather_info.get("suggestion", "")
                    logger.info(f"🌤️ 天氣資訊：您目前所在地區 {temp}°C - {weather_info.get('weather_description', '')}")
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
            
            # 無法判斷的圖片視為衣物（保守策略）
            if unknown_images:
                logger.info(f"   ℹ️ 將 {len(unknown_images)} 張無法判斷的圖片視為衣物")
                clothing_images.extend(unknown_images)
        
        # 4. 🔥 決定照片和衣物來源（四種策略）
        final_face_photo = None
        final_clothing_items = []
        photo_source = ""
        strategy = ""
        
        has_uploaded_face = len(face_images) > 0
        has_uploaded_clothing = len(clothing_images) > 0
        
        if has_uploaded_face and has_uploaded_clothing:
            # 策略 3: 上傳衣物 + 臉部
            strategy = "策略3: 上傳衣物+臉部"
            final_face_photo = face_images[0]  # 使用第一張臉部照片
            photo_source = "上傳臉部照片"
            
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
            strategy = "策略1: 上傳臉部+衣櫥衣物"
            final_face_photo = face_images[0]
            photo_source = "上傳臉部照片"
            
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
            strategy = "策略2: 上傳衣物+用戶頭貼"
            
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
            strategy = "策略4: 用戶頭貼+衣櫥衣物"
            
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

        try:
            # 1️⃣ 檢查是否只詢問天氣（不包含穿搭）
            if self.is_weather_only_request(user_input):
                logger.info("🌤️ 偵測到純天氣查詢，返回天氣資訊。")
                if weather_info:
                    weather_text = f"""📍 您目前所在地區的天氣資訊：

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

                # 檢查是否有衣物可用（來自策略決策）
                if not final_clothing_items:
                    logger.warning("沒有可用的衣物（策略決策結果為空），無法進行圖片生成。")
                    return self._generate_outfit_fallback_text(user_input, wardrobe_items, weather_info, weather_advice)

                logger.info(f"🧾 使用 {len(final_clothing_items)} 件衣物（來自{strategy}）")

                # 使用 ImageGenerationService 的生成方法
                logger.info(f"🛠️ 準備呼叫 img_gen_service.generate_tryon_image()")
                logger.info(f"    📸 照片來源: {photo_source}")
                logger.info(f"    📸 是否傳遞用戶照片: {'是' if final_face_photo else '否 (使用預設模特兒)'}")

                generation_result = await img_gen_service.generate_tryon_image(
                    prompt=user_input,
                    clothing_items=final_clothing_items,  # 🔥 使用策略決策的衣物
                    user_photo_base64=final_face_photo  # 🔥 使用策略決策的臉部照片
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
                        
                        # 建立詳細說明文字
                        clothing_names = "、".join([item["name"] for item in final_clothing_items[:3]])
                        if len(final_clothing_items) > 3:
                            clothing_names += f" 等 {len(final_clothing_items)} 件"
                        
                        response_parts = [f"好的！這是為您生成的穿搭建議。"]
                        
                        # 加入天氣資訊
                        if weather_info:
                            response_parts.append(
                                f"🌤️ 根據您目前所在地區的天氣（{weather_info['temperature']}°C，{weather_info['weather_description']}）"
                            )
                        
                        # 加入衣櫃資訊
                        if final_clothing_items:
                            response_parts.append(f"👔 搭配您衣櫃裡的{clothing_names}")
                        
                        response_parts.append(f"📸 照片來源：{photo_source}")
                        
                        response_text = "\n".join(response_parts)

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