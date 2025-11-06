#app/services/fashion_advisor.py
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import base64
from io import BytesIO
from urllib.parse import unquote
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
                        item = ClothingItem(
                            category=category,
                            name=f"{category} - {name}",
                            cover_image_url=blob.public_url 
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
        
        
  
    def _fuse_outfit_images_with_gemini(self, wardrobe_items: List[ClothingItem], user_input: str) -> Optional[str]:
        """使用 Gemini 分析衣物圖片，再用 Imagen 生成穿搭圖."""
        
        # 1. 將 wardrobe_items 中的 GCS URL 下載並轉為 Part 對象
        content_parts = []
        successful_parts = []
        item_descriptions = []
        
        for item in wardrobe_items:
            # 判斷是否為 GCS URL
            if item.cover_image_url and "https://storage.googleapis.com/" in item.cover_image_url: 
                part = self._download_gcs_to_part(item.cover_image_url)
                if part:
                    successful_parts.append(part)
                    item_descriptions.append(f"{item.category}: {item.name}")
                else:
                    logger.warning(f"未能下載或轉換圖片: {item.cover_image_url}。")
            else:
                logger.warning(f"衣物 '{item.name}' 的 URL 無效或為模擬數據，將使用文字描述替代。")
                item_descriptions.append(f"{item.category}: {item.name}")
                 
        if len(successful_parts) < 2:
            # 如果圖片少於 2 張，直接用 Imagen 生成
            logger.warning("圖片數量不足 2 張，直接使用 Imagen Text-to-Image。")
            outfit_prompt = f"A realistic full-body photo of a young Taiwanese woman wearing {', '.join(item_descriptions)}. Natural outdoor setting, clear daytime, professional fashion photography."
            return self._call_image_generation_api_fallback(outfit_prompt)

        # 2. 使用 Gemini 分析衣物並生成詳細的穿搭描述
        logger.info(f"使用 Gemini 分析 {len(successful_parts)} 件衣物...")
        
        # 將圖片 Parts 加入內容
        content_parts.extend(successful_parts)
        
        # Gemini 分析指令（生成文本描述）
        analysis_instruction = (
            f"你是專業的時尚造型師。使用者說：「{user_input}」\n\n"
            f"以上是使用者衣櫃中的 {len(successful_parts)} 件衣物圖片（{', '.join(item_descriptions)}）。\n\n"
            "請根據這些衣物的實際外觀（顏色、款式、材質、細節），生成一段**英文的詳細穿搭描述**，用於生成一張專業的全身穿搭照。\n"
            "描述格式：A realistic full-body fashion photo of a young Taiwanese woman wearing [詳細描述每件衣物的顏色、款式、材質]。"
            "描述中要包含：姿勢、背景、光線、拍攝風格等專業攝影要素。\n"
            "只輸出英文描述，不要有其他內容。"
        )
        
        content_parts.append(analysis_instruction)
        
        try:
            # 3. 呼叫 Gemini 生成文本描述
            response: GenerationResponse = self.text_model.generate_content(content_parts)
            
            if not response.candidates or not response.candidates[0].content.parts:
                logger.warning("Gemini 未返回有效的分析結果，使用預設描述。")
                outfit_prompt = f"A realistic full-body photo of a young Taiwanese woman wearing {', '.join(item_descriptions)}. Natural outdoor setting, professional fashion photography."
            else:
                # 獲取 Gemini 生成的文本描述
                outfit_prompt = response.candidates[0].content.parts[0].text.strip()
                logger.info(f"Gemini 生成的穿搭描述: {outfit_prompt[:150]}...")
            
            # 4. 使用 Imagen 生成圖片
            logger.info("使用 Imagen 生成穿搭圖片...")
            return self._call_image_generation_api_fallback(outfit_prompt)

        except Exception as e:
            logger.error(f"呼叫 Gemini 分析失敗: {e}", exc_info=True)
            # 失敗時使用預設描述
            outfit_prompt = f"A realistic full-body photo of a young Taiwanese woman wearing {', '.join(item_descriptions)}. Natural outdoor setting, professional fashion photography."
            return self._call_image_generation_api_fallback(outfit_prompt)
        
    
    
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


    def process_user_input(self, user_id: str, user_input: str, user_image_data: Optional[str] = None) -> Dict[str, Any]:
        """
        處理使用者輸入，如果偵測到穿搭請求，則嘗試生成圖片；否則進行一般聊天。
        """
        logger.info(f"開始處理User '{user_id}'的輸入: '{user_input}'，是否有使用者圖片: {bool(user_image_data)}")
        
        if not self.text_model and not self.image_model:
             logger.critical("Gemini 和 Imagen 模型都未初始化。")
             return {"type": "text", "text": "嚴重錯誤：服裝建議服務未啟動。請檢查 GCP/Vertex AI 憑證和設定。"}
         
        wardrobe_items = self.get_wardrobe_items(user_id)
        
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

    def _download_gcs_to_part(self, gcs_url: str) -> Optional[Part]:
        """從 GCS URL 下載圖片並轉換為 Vertex AI Part 對象。"""
        try:
            if gcs_url.startswith("https://storage.googleapis.com/"):
                parts = gcs_url[len("https://storage.googleapis.com/"):].split('/', 1)
                bucket_name = parts[0]
                blob_name = unquote(parts[1])
            else:
                # 模擬數據或格式錯誤，無法處理
                logger.error(f"GCS URL 格式錯誤或非 GCS URL: {gcs_url}")
                return None
            
            blob = self.gcs_client.bucket(bucket_name).blob(blob_name)           
            image_bytes = blob.download_as_bytes()

            # 確定 MIME 類型並直接使用字節數據創建 Part
            mime_type = blob.content_type or "image/png"
            
            return Part.from_data(data=image_bytes, mime_type=mime_type)

        except Exception as e:
            logger.error(f"下載或轉換 GCS 圖片失敗: {gcs_url}, 錯誤: {e}", exc_info=True)
            return None
        
        
        
        
        
    def _get_selected_clothing_items(self, user_id: str, selected_items: List[dict]) -> List[ClothingItem]:
        """
        根據前端傳入的精確 ID，從 GCS 檢查並獲取衣物的完整對象（包含 GCS URL）。
        
        ⚠️ 注意：由於您沒有提供資料庫層，我們這裡做一個簡化假設：
        我們將嘗試用 selected_items 中的 ID/name/category 去 GCS 裡匹配，
        但更嚴謹的做法是根據 item.id 從資料庫查詢完整的 ClothingItem 資訊，包括圖片 URL。
        """
        all_wardrobe_items = self.get_wardrobe_items(user_id) # 獲取所有衣物
        selected_ids = {item.id for item in selected_items} # 假設前端傳入的 item 有 id 欄位

        # 這裡由於 ClothingItemIn 沒有 cover_image_url，我們必須從所有衣櫃中匹配。
        # 由於您沒有提供一個包含 URL 的 ClothingItemIn 類別，
        # 這裡會創建一個新的 ClothingItem 列表，並嘗試在 GCS 獲取的清單中找到對應的 URL
        
        # 簡化匹配邏輯 (假設前端傳入的 name 和 category 足夠匹配)
        # 由於您在 VirtualFitting.jsx 中使用的是 item.img，這裡需要調整前端傳輸內容，
        # 或者假設 GCS 圖片名與 item.name 相關聯。
        
        # 為了讓後端能工作，我們修改邏輯：直接利用 get_wardrobe_items 的結果來篩選。
        
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
    
    
    
    
    
    
    def process_fitting_request(self, user_id: str, user_input: str, selected_items: List[dict]) -> Dict[str, Any]:
        """
        專門用於虛擬試衣頁面，根據精確選擇的衣物生成圖片。
        """
        logger.info(f"處理虛擬試衣生成請求：User ID: {user_id}, Items: {len(selected_items)}")
        
        # 1. 獲取選中衣物的完整資訊 (含 GCS URL)
        wardrobe_items = self._get_selected_clothing_items(user_id, selected_items)
        
        if not wardrobe_items:
            return {"type": "text", "text": "請先在衣櫃中選擇至少一件衣物。"}
            
        # 2. 呼叫核心的圖片生成邏輯 (多圖融合)
        generated_image_url = self._fuse_outfit_images_with_gemini(
            wardrobe_items=wardrobe_items, 
            user_input=user_input
        )
        
        # 3. 處理結果
        if generated_image_url:
            return {
                "type": "image",
                "url": generated_image_url,
                "text": f"好的，這是根據您選中的 {len(wardrobe_items)} 件衣物生成的穿搭建議："
            }
        else:
            # 如果圖片生成失敗，退回純文字建議
            return self.chat_with_gemini(user_input, wardrobe_items)