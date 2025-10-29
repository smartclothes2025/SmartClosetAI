import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image as PILImage # 導入 PIL Image 模組

# 載入環境變數
from dotenv import load_dotenv
load_dotenv() # 確保在 main.py 或 app.py 中呼叫過一次

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.preview.vision_models import ImageGenerationModel

class ClothingItem: # 將 WardrobeItem 改名為 ClothingItem 以保持一致
    def __init__(self, category, name, cover_image_url):
        self.category = category
        self.name = name # 新增一個 name 屬性用於生成 prompt
        self.cover_image_url = cover_image_url

class SessionLocal:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def query(self, model):
        # 模擬資料庫中有一些衣物
        return [
            ClothingItem(category="tops", name="白色T恤", cover_image_url="top1.png"),
            ClothingItem(category="pants", name="藍色牛仔褲", cover_image_url="pants1.png"),
            ClothingItem(category="shoes", name="休閒運動鞋", cover_image_url="shoes1.png"),
            ClothingItem(category="outerwear", name="黑色夾克", cover_image_url="jacket1.png"),
        ]
    def all(self):
        return self.query(ClothingItem)
    def close(self):
        pass
# --- 模擬導入結束 ---

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FashionAdvisor:

    CATEGORY_MAP = {
        "tops": "tops",
        "pants": "bottoms",
        "skirts": "bottoms",
        "dresses": "bottoms", # 洋裝也歸類到下身來簡化處理
        "outerwear": "outerwear",
        "shoes": "shoes",
        "accessories": "accessories",
    }
    
    # 這個目錄映射用於從 'uploads' 中找到原始圖片的路徑
    CATEGORY_DIR_MAP = {
        "tops": "tops",
        "bottoms": "pants", # 假設褲子和裙子都放在 'pants' 目錄下
        "shoes": "shoes",
        "outerwear": "outerwear",
        "accessories": "bags",
    }
    
    def __init__(self, wardrobe_root: str = "uploads"): # 假設圖片上傳到 'uploads'
        self.wardrobe_root = wardrobe_root # <-- 修正了 U+00A0 字元
        
        # --- 讀取環境變數 ---
        self.gcp_project_id = os.getenv("GCP_PROJECT_ID")
        self.gcp_location = os.getenv("GCP_LOCATION", "us-central1") # Vertex AI 需要地區
        self.gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")
        # --- Vertex AI 不需要 API Key, 它會使用 GOOGLE_APPLICATION_CREDENTIALS ---
        # self.gemini_api_key = os.getenv("GEMINI_API_KEY") # 這行可以刪除或註解
        
        if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            logger.error("重大錯誤：GOOGLE_APPLICATION_CREDENTIALS 未在 .env 中設定！")
        
        logger.info("--- FashionAdvisor 初始化開始 (使用 Vertex AI) ---")
        logger.info(f"讀取到的 GCP_PROJECT_ID: '{self.gcp_project_id}'")
        logger.info(f"讀取到的 GCP_LOCATION: '{self.gcp_location}'") # 確保 .env 中有設定
        logger.info(f"使用的憑證檔案: '{os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}'")

        # --- 初始化 Vertex AI ---
        try:
            if not self.gcp_project_id or not self.gcp_location:
                raise ValueError("GCP_PROJECT_ID 和 GCP_LOCATION 必須在 .env 中設定")
            
            # Vertex AI SDK 會自動讀取 GOOGLE_APPLICATION_CREDENTIALS
            vertexai.init(project=self.gcp_project_id, location=self.gcp_location)
            
            # 使用 Vertex AI 的模型名稱 (例如 "gemini-1.0-pro" 或 "gemini-1.5-flash-001")
            self.text_model = GenerativeModel("gemini-2.5-flash") 
            # 使用 Imagen 模型進行圖片生成
            self.image_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            logger.info(f"Vertex AI (GCP) API 初始化成功")
            logger.info(f"Imagen 圖片生成模型初始化成功")       
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


        if not os.path.exists(self.wardrobe_root):
            logger.warning(f"'{self.wardrobe_root}' 目錄不存在，可能無法讀取衣物圖片。")
        logger.info(f"FashionAdvisor 初始化完成，衣櫃根目錄: {self.wardrobe_root}")

    def get_wardrobe_items(self) -> List[ClothingItem]: # 返回 ClothingItem 對象列表
        """從資料庫獲取所有衣物項目"""
        items = []
        db = None
        try:
            with SessionLocal() as db:
                items = db.all() # 這裡應該是 db.query(ClothingItem).all()
                logger.info(f"從資料庫抓到 {len(items)} 件衣服。")
        except Exception as e:
            logger.error(f"從資料庫獲取衣物清單時發生錯誤: {e}", exc_info=True)
        finally:
            if db:
                db.close()
                logger.info("資料庫會話已關閉。")
        return items

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

    def _call_image_generation_api(self, user_input: str, wardrobe_items: List[ClothingItem], user_image_data: Optional[str] = None) -> Optional[str]:
        """
        使用 Vertex AI Imagen 模型生成穿搭圖片
        """
        if not self.image_model:
            logger.error("Imagen 模型未初始化，無法生成圖片。")
            return None

        # 根據衣物清單構建 prompt
        outfit_descriptions = [item.name for item in wardrobe_items if item.name]
        outfit_prompt_part = ", ".join(outfit_descriptions) if outfit_descriptions else "時尚穿搭"
        
        # 構建適合圖片生成的 prompt
        image_prompt = f"A stylish fashion outfit featuring {outfit_prompt_part}, professional fashion photography, clean background, high quality, realistic"
        
        logger.info(f"呼叫 Imagen 模型生成圖片，prompt: '{image_prompt}'")
        
        try:
            # 使用 Imagen 生成圖片
            response = self.image_model.generate_images(
                prompt=image_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )
            
            if response.images and len(response.images) > 0:
                logger.info("Imagen 成功生成圖片")
                
                # 將圖片轉換為 bytes 並上傳到 GCS
                image = response.images[0]
                
                # 將 PIL Image 轉換為 bytes
                img_byte_arr = BytesIO()
                image._pil_image.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()
                
                # 上傳到 GCS
                public_url = self._upload_image_to_gcs(image_bytes, folder="generated_outfits")
                
                if public_url:
                    logger.info(f"圖片已上傳到 GCS: {public_url}")
                    return public_url
                else:
                    logger.error("圖片上傳到 GCS 失敗")
                    return None
            else:
                logger.warning("Imagen 模型未返回圖片。")
                return None

        except Exception as e:
            logger.error(f"呼叫 Imagen API 失敗: {e}", exc_info=True)
            return None

    def process_user_input(self, user_input: str, user_image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        處理使用者輸入，如果偵測到穿搭請求，則嘗試生成圖片；否則進行一般聊天。
        """
        logger.info(f"開始處理使用者輸入: '{user_input}'，是否有使用者圖片: {bool(user_image_data)}")
        
        wardrobe_items = self.get_wardrobe_items()
        
        try:
            if self.is_outfit_request(user_input) and wardrobe_items:
                logger.info("偵測到穿搭請求，且衣櫃非空。")
                
                # 這裡直接傳遞整個 ClothingItem 對象列表給影像生成 API
                generated_image_url = self._call_image_generation_api(user_input, wardrobe_items, user_image_data)
                
                if generated_image_url:
                    logger.info(f"影像已生成，URL: {generated_image_url}")
                    return {
                        "type": "image",
                        "url": generated_image_url,
                        "text": "好的，這是為您生成的穿搭建議："
                    }
                else:
                    logger.error("影像生成失敗，轉為一般聊天。")
            
            # 如果非穿搭需求，或衣櫃為空，或影像生成失敗，進行一般聊天
            logger.info("進行一般聊天模式。")
            
            if not self.text_model:
                logger.error("Gemini API 文本模型未初始化，無法執行聊天功能。")
                return {"type": "text", "text": "錯誤：Gemini API 未設定，請檢查 GEMINI_API_KEY。"}

            prompt = f"你是一個智慧穿搭助手，使用者說：'{user_input}'。請自然、專業地回答，提供穿搭方面的建議。"
            
            # 使用 self.text_model (來自 Gemini API)
            response = self.text_model.generate_content(prompt) 
            gemini_text = response.text.strip() if response.text else ""
            
            if not gemini_text:
                logger.warning("Gemini 聊天模型回傳空字串。")
                return {"type": "text", "text": "抱歉，我暫時無法回答這個問題。"}
            
            logger.info(f"Gemini 聊天回應: {gemini_text[:100]}...")
            return {"type": "text", "text": gemini_text}

        except Exception as e:
            logger.error(f"FashionAdvisor 處理錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}