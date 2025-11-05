#app/services/fashion_advisor.py
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image as PILImage # 導入 PIL Image 模組

# 載入環境變數
from dotenv import load_dotenv
import os
# 強制重新載入環境變數，覆蓋已存在的值
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path, override=True)

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationResponse
from vertexai.preview.vision_models import ImageGenerationModel

class ClothingItem: # 將 WardrobeItem 改名為 ClothingItem 以保持一致
    def __init__(self, category, name, cover_image_url):
        self.category = category
        self.name = name # 新增一個 name 屬性用於生成 prompt
        self.cover_image_url = cover_image_url
        

def get_real_wardrobe_data() -> List[ClothingItem]:
        """
        *** 請將此函數替換為您實際連接資料庫 (如 SQLAlchemy 或其它 ORM) 的程式碼 ***
        
        這個函數的目標是從資料庫中取出使用者衣櫥中所有衣物項目的清單，
        並且每一項的 'cover_image_url' 必須是一個**完整的 GCS 公開 URL**。
        
        由於無法存取您的資料庫，這裡我們返回一個硬編碼的 GCS URL 範例，
        讓您可以測試多圖融合功能，請替換為您圖片上傳後寫入資料庫的真實 URL。
        """
        
        # 🔴 請將下方的 URL 替換為您實際在 GCS 上傳的幾張圖片的公共鏈接！
        # 🔴 確保這些 URL 是可公開訪問的，否則 _download_gcs_to_part 會失敗。
        # 
        # 根據您提供的圖片，假設您從 'avatars' 或其他目錄中選取圖片
        
        GCS_BUCKET_URL_PREFIX = f"https://storage.googleapis.com/{os.getenv('GCS_BUCKET_NAME')}"

        # 模擬從資料庫讀取到的真實數據
        return [
            ClothingItem(
                category="tops", 
                name="白色T恤 (V領)", 
                cover_image_url=f"{GCS_BUCKET_URL_PREFIX}/avatars/8823573a-6d4f-441b-b15b-95f90781fb23/tshirt.jpg" # 替換為真實路徑
            ),
            ClothingItem(
                category="pants", 
                name="修身深藍牛仔褲", 
                cover_image_url=f"{GCS_BUCKET_URL_PREFIX}/avatars/8823573a-6d4f-441b-b15b-95f90781fb23/褲子.jpg" # 替換為真實路徑
            ),
            ClothingItem(
                category="shoes", 
                name="黑色休閒運動鞋", 
                cover_image_url=f"{GCS_BUCKET_URL_PREFIX}/avatars/8823573a-6d4f-441b-b15b-95f90781fb23/上2.jpg" # 替換為真實路徑
            ),
            ClothingItem(
                category="outerwear", 
                name="米白色薄夾克", 
                cover_image_url=f"{GCS_BUCKET_URL_PREFIX}/avatars/8823573a-6d4f-441b-b15b-95f90781fb23/上.jpg" # 替換為真實路徑
            ),
        ]
    
    
    
    
    
    

class SessionLocal:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def query(self, model):
        # 🔴 每次查詢都直接調用獲取真實數據的模擬函數
        return get_real_wardrobe_data()
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
    
    def __init__(self):
        """初始化 FashionAdvisor，所有圖片從 GCS 讀取"""
        
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

        logger.info(f"FashionAdvisor 初始化完成 (僅使用 GCS，不使用本地儲存)")

    
    
    
    def get_wardrobe_items(self) -> List[ClothingItem]:
        """根據衣物清單生成摘要，用於給 Gemini 的 Prompt。"""
        items = [] 
        db = None
        
        try:
            with SessionLocal() as db:
                # 這裡的 db.all() 返回的列表賦值給了 items
                items = db.all() 
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
        
        
    # def _generate_imagen_prompt_with_gemini(self, wardrobe_items: List[ClothingItem], user_input: str) -> Optional[str]:
    #     """
    #     使用 Gemini 2.5 Flash 讀取衣物圖片，並生成高精度的 Imagen Prompt。
    #     """
    #     if not self.text_model or not self.gcs_client:
    #         logger.error("Gemini 模型或 GCS 客戶端未初始化，無法生成 Prompt。")
    #         return None
        
    #     # 1. 準備 Gemini 的內容列表 (Content Parts)
    #     content_parts = []
        
    #     # 系統指令：要求 Gemini 觀察圖片並生成 Prompt
    #     system_instruction = (
    #         "你是一個專業的時尚分析師。請仔細觀察接下來提供的每一張衣物圖片，並結合使用者要求 ('"
    #         f"{user_input}')，生成一個**單一、連續**且**極其細節化**的圖像生成 Prompt。"
    #         "Prompt 必須清晰描述：模特兒穿著這些衣物後的**款式、材質、顏色深淺**，並要求**休閒、寫實、高畫質**的風格。"
    #         "請勿在輸出中包含任何額外解釋或標點符號，只返回可直接用於 Imagen 的 Prompt 文字。"
    #         "範例格式: A young woman wearing a slim-fit, crew-neck cotton white T-shirt, paired with light-wash, straight-leg denim jeans, with a slightly oversized black leather jacket, and white retro running sneakers. Outdoor setting, natural light, realistic photo."
    #     )
    #     content_parts.append(system_instruction)

    #     # 2. 下載並添加衣物圖片
    #     successful_items_desc = []
    #     for item in wardrobe_items:
    #         # 這裡假設 cover_image_url 是 GCS 的公開 URL
    #         if item.cover_image_url and item.cover_image_url != "top1.png": # 排除模擬數據中的 'top1.png' 等
    #             part = self._download_gcs_to_part(item.cover_image_url)
    #             if part:
    #                 content_parts.append(part)
    #                 successful_items_desc.append(item.name)
    #         else:
    #              # 對於模擬數據，至少確保文字描述被納入考慮
    #             successful_items_desc.append(item.name)

    #     if len(content_parts) == 1: # 只有系統指令，沒有成功載入任何圖片
    #          logger.warning("未能成功載入任何 GCS 圖片，將使用文字描述生成 Prompt。")
    #          # 退回到純文字生成 Prompt (類似您原始的做法，但風格改為寫實)
    #          outfit_prompt_part = ", ".join(successful_items_desc) if successful_items_desc else "時尚穿搭"
    #          return f"A casual and realistic outfit for daily life featuring {outfit_prompt_part}, photographed outdoors on a sunny day, natural light, no heavy photo editing."


    #     logger.info(f"呼叫 Gemini 2.5 Flash 讀取 {len(content_parts)-1} 張圖片並生成 Prompt...")
        
    #     try:
    #         # 3. 呼叫 Gemini 2.5 Flash
    #         response: GenerationResponse = self.text_model.generate_content(content_parts)
    #         gemini_prompt = response.text.strip()
            
    #         if gemini_prompt:
    #             logger.info(f"Gemini 生成的 Prompt (部分): {gemini_prompt[:100]}...")
    #             return gemini_prompt
    #         else:
    #             logger.warning("Gemini 未能生成有效的 Prompt。")
    #             return None
    #     except Exception as e:
    #         logger.error(f"呼叫 Gemini 進行 Prompt 生成失敗: {e}", exc_info=True)
    #         return None
        
    def _fuse_outfit_images_with_gemini(self, wardrobe_items: List[ClothingItem], user_input: str) -> Optional[str]:
        """
        使用 Gemini 2.5 Flash 融合多張衣物圖片到一個亞洲模特身上。
        """
        if not self.text_model or not self.gcs_client:
            logger.error("Gemini 模型或 GCS 客戶端未初始化，無法執行融合任務。")
            return None
        
        content_parts = []
        
        # 1. 下載並添加衣物圖片
        successful_parts = []
        item_names = []
        
        # 🔴 設置亞洲模特的參考圖片 (使用一個通用的佔位符，實際應該是 GCS 上的一個亞洲人模特圖)
        # 為了簡化，我們將換裝指令視為主要內容。
        
        for item in wardrobe_items:
            # 🔴 判斷是否為 GCS URL (簡單判斷是否包含 https://storage.googleapis.com/)
            if item.cover_image_url and "https://storage.googleapis.com/" in item.cover_image_url: 
                part = self._download_gcs_to_part(item.cover_image_url)
                if part:
                    successful_parts.append(part)
                    item_names.append(item.name)
                else:
                    logger.warning(f"未能下載或轉換圖片: {item.cover_image_url}。")
            else:
                 logger.warning(f"衣物 '{item.name}' 的 URL 無效或為模擬數據，將使用文字描述替代。")
                 item_names.append(item.name)
                 
        if len(successful_parts) < 2:
             # 如果圖片少於 2 張，很難執行融合，退回 Text-to-Image Fallback
             logger.error("至少需要 2 張以上圖片才能執行融合換裝任務，將退回 Text-to-Image Fallback。")
             outfit_prompt = f"A realistic full-body photo of a young Taiwanese woman wearing a {', '.join(item_names)}. Natural outdoor setting, clear daytime, professional photo quality."
             return self._call_image_generation_api_fallback(outfit_prompt)

        # 2. 構建融合指令
        # 🔴 將所有圖片 Part 加入內容列表 (這是 Gemini 執行多模態的關鍵)
        content_parts.extend(successful_parts)
        
        fusion_instruction = (
            "指令：你是一名 AI 換裝設計師。請將上方這些**獨立的衣物圖片** (上衣、褲子、外套、鞋子等) **無縫地合成並穿戴**到一個**亞洲年輕女性 (台灣人臉孔)** 模特兒身上。"
            "合成後的圖片必須看起來像一張**寫實、專業的全身穿搭照**，保留衣物原始的**款式和細節**。"
            "使用者要求：'{user_input}'。請根據使用者的要求選擇合適的姿勢和背景。"
            "請直接輸出合成後的新圖片，不需要任何文字描述。"
        ).format(user_input=user_input)
        
        # 🔴 將文字指令放在最後
        content_parts.append(fusion_instruction)

        logger.info(f"呼叫 Gemini 2.5 Flash 進行多圖融合，包含 {len(successful_parts)} 張圖片...")
        
        try:
            # 3. 呼叫 Gemini 進行多模態內容生成
            response: GenerationResponse = self.text_model.generate_content(content_parts)
            
            # 4. 處理圖像輸出
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.mime_type.startswith('image/') and part.inline_data:
                        # 🔴 圖片數據是 base64 編碼的
                        image_bytes = base64.b64decode(part.inline_data.data)
                        
                        # 5. 上傳到 GCS
                        public_url = self._upload_image_to_gcs(image_bytes, folder="fused_outfits")
                        return public_url
                        
            logger.warning("Gemini 融合任務未返回圖片 Part。")
            return None

        except Exception as e:
            logger.error(f"呼叫 Gemini 融合 API 失敗: {e}", exc_info=True)
            return None
        

    # def _call_image_generation_api(self, user_input: str, wardrobe_items: List[ClothingItem], user_image_data: Optional[str] = None) -> Optional[str]:
    #     """
    #     使用 Vertex AI Imagen 模型生成穿搭圖片
    #     """
    #     if not self.image_model:
    #         logger.error("Imagen 模型未初始化，無法生成圖片。")
    #         return None

    #     # 根據衣物清單構建 prompt
    #     outfit_descriptions = [item.name for item in wardrobe_items if item.name]
    #     outfit_prompt_part = ", ".join(outfit_descriptions) if outfit_descriptions else "時尚穿搭"
        
    #     # 構建適合圖片生成的 prompt
    #     image_prompt = f"A stylish fashion outfit featuring {outfit_prompt_part}, professional fashion photography, clean background, high quality, realistic"
        
    #     logger.info(f"呼叫 Imagen 模型生成圖片，prompt: '{image_prompt}'")
        
    #     try:
    #         # 使用 Imagen 生成圖片
    #         response = self.image_model.generate_images(
    #             prompt=image_prompt,
    #             number_of_images=1,
    #             aspect_ratio="1:1",
    #             safety_filter_level="block_some",
    #             person_generation="allow_adult"
    #         )
            
    #         if response.images and len(response.images) > 0:
    #             logger.info("Imagen 成功生成圖片")
                
    #             # 將圖片轉換為 bytes 並上傳到 GCS
    #             image = response.images[0]
                
    #             # 將 PIL Image 轉換為 bytes
    #             img_byte_arr = BytesIO()
    #             image._pil_image.save(img_byte_arr, format='PNG')
    #             image_bytes = img_byte_arr.getvalue()
                
    #             # 上傳到 GCS
    #             public_url = self._upload_image_to_gcs(image_bytes, folder="generated_outfits")
                
    #             if public_url:
    #                 logger.info(f"圖片已上傳到 GCS: {public_url}")
    #                 return public_url
    #             else:
    #                 logger.error("圖片上傳到 GCS 失敗")
    #                 return None
    #         else:
    #             logger.warning("Imagen 模型未返回圖片。")
    #             return None

    #     except Exception as e:
    #         logger.error(f"呼叫 Imagen API 失敗: {e}", exc_info=True)
    #         return None
    
    def _call_image_generation_api_fallback(self, image_prompt: str) -> Optional[str]:
         """作為多圖融合失敗時的 Text-to-Image 備選方案"""
         if not self.image_model: return None
         logger.info(f"退回 Imagen Text-to-Image 模式，Prompt: {image_prompt[:50]}...")
         try:
            response = self.image_model.generate_images(
                prompt=image_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )
            
            if response.images and len(response.images) > 0:
                image = response.images[0]
                img_byte_arr = BytesIO()
                image._pil_image.save(img_byte_arr, format='PNG')
                image_bytes = img_byte_arr.getvalue()
                return self._upload_image_to_gcs(image_bytes, folder="generated_outfits_fallback")
            return None
         except Exception as e:
            logger.error(f"Imagen fallback 失敗: {e}")
            return None

    def chat_with_gemini(self, user_input: str, wardrobe_items: List[ClothingItem]) -> Dict[str, Any]:
        """
        使用 Gemini 模型進行一般聊天，並整合衣櫃清單。
        """
        logger.info("進行一般聊天模式 (Gemini)。")
        
        if not self.text_model:
            logger.error("Gemini 文本模型未初始化，無法執行聊天功能。")
            return {"type": "text", "text": "錯誤：聊天服務未正確設定。請檢查服務器的 Vertex AI/GCP 設定。"}

        try:
            # 使用傳入的 wardrobe_items，不需要再次調用 get_wardrobe_items
            # 將 wardrobe_items 轉換為易於閱讀的描述
            wardrobe_summary = ", ".join([f"{item.category}: {item.name}" for item in wardrobe_items]) if wardrobe_items else "衣櫃目前是空的"
            
            # 將系統指令和用戶輸入整合到 prompt 中
            full_prompt = f"""你是一個智慧穿搭助手，請根據使用者的問題和他們現有的衣櫃清單提供專業建議。
如果使用者是詢問穿搭建議，請盡可能在文字上給出包含他們現有衣物的搭配方案，即使圖片生成失敗也一樣。

使用者的衣櫃清單: {wardrobe_summary}

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
            logger.error(f"與 Gemini 聊天時發生錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}


    def process_user_input(self, user_input: str, user_image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        處理使用者輸入，如果偵測到穿搭請求，則嘗試生成圖片；否則進行一般聊天。
        """
        logger.info(f"開始處理使用者輸入: '{user_input}'，是否有使用者圖片: {bool(user_image_data)}")
        
        if not self.text_model and not self.image_model:
             logger.critical("Gemini 和 Imagen 模型都未初始化。")
             return {"type": "text", "text": "嚴重錯誤：服裝建議服務未啟動。請檢查 GCP/Vertex AI 憑證和設定。"}
         
        wardrobe_items = self.get_wardrobe_items()
        
        try:
            if self.is_outfit_request(user_input) and wardrobe_items:
                logger.info("偵測到穿搭請求，執行 Gemini 多圖融合。")
                
                # 這裡直接傳遞整個 ClothingItem 對象列表給影像生成 API
                generated_image_url = self._fuse_outfit_images_with_gemini(wardrobe_items, user_input)
                
                
                if generated_image_url:
                    logger.info(f"影像已生成，URL: {generated_image_url}")
                    return {
                        "type": "image",
                        "url": generated_image_url,
                        "text": "好的，這是為您生成的穿搭建議："
                    }
                else:
                    logger.error("影像生成失敗，轉為一般聊天。")
                    # 影像生成失敗，直接呼叫 Gemini 聊天
                    return self.chat_with_gemini(user_input, wardrobe_items)
            
            # 如果非穿搭需求或衣櫃為空，進行一般聊天
            return self.chat_with_gemini(user_input, wardrobe_items)

        except Exception as e:
            logger.error(f"FashionAdvisor 處理錯誤: {str(e)}", exc_info=True)
            return {"type": "text", "text": f"服務器內部錯誤：{str(e)}"}
        
        
        
        
        # fashion_advisor.py (新增輔助方法)
    def _download_gcs_to_part(self, gcs_url: str) -> Optional[Part]:
        """從 GCS URL 下載圖片並轉換為 Vertex AI Part 對象。"""
        try:

            # 🔴 修改：支援 https://storage.googleapis.com/ 格式的 URL，從 URL 提取 bucket 和 blob
            if gcs_url.startswith("https://storage.googleapis.com/"):
                parts = gcs_url[len("https://storage.googleapis.com/"):].split('/', 1)
                bucket_name = parts[0]
                blob_name = parts[1]
            else:
                # 模擬數據或格式錯誤，無法處理
                logger.error(f"GCS URL 格式錯誤或非 GCS URL: {gcs_url}")
                return None
            
            blob = self.gcs_client.bucket(bucket_name).blob(blob_name)           
            image_bytes = blob.download_as_bytes()

            # 使用 PIL 載入並轉換為 Part
            image_pil = PILImage.open(BytesIO(image_bytes))
            
            return Part.from_image(image=image_pil)

        except Exception as e:
            logger.error(f"下載或轉換 GCS 圖片失敗: {gcs_url}, 錯誤: {e}", exc_info=True)
            return None