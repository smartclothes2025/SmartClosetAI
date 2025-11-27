# app/services/image_classifier.py
import base64
import logging
from typing import Dict, List, Literal
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import os
from dotenv import load_dotenv

# 載入環境變數
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path, override=True)

logger = logging.getLogger(__name__)

class ImageClassifier:
    """使用 Gemini Vision API 分類圖片為臉部或衣物"""
    
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            # 使用 Gemini 2.0 Flash（更快速且準確）
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            logger.info("✅ ImageClassifier 初始化成功（使用 Gemini 2.0 Flash）")
        else:
            self.model = None
            logger.warning("⚠️ GEMINI_API_KEY 未設定，圖片分類功能將無法使用")
    
    def classify_image(self, image_base64: str) -> Literal["face", "clothing", "unknown"]:
        """
        分類單張圖片
        
        Args:
            image_base64: Base64 編碼的圖片（不含 data:image 前綴）
            
        Returns:
            "face": 臉部照片
            "clothing": 衣物照片
            "unknown": 無法判斷
        """
        if not self.model:
            logger.error("❌ Gemini 模型未初始化")
            return "unknown"
        
        try:
            # 解碼圖片
            img_bytes = base64.b64decode(image_base64)
            img = Image.open(BytesIO(img_bytes))
            
            # 準備 prompt
            prompt = """請分析這張圖片，並判斷它主要是以下哪一類：

1. **臉部照片**: 圖片中有清晰的人臉（可以是自拍、大頭照、證件照等），臉部是圖片的主要焦點
2. **衣物照片**: 圖片中主要是衣物、服裝單品（例如：上衣、褲子、裙子、鞋子、配件等），可能有模特兒穿著或平鋪拍攝

請只回答以下其中一個選項（不需要解釋）：
- FACE（如果主要是臉部照片）
- CLOTHING（如果主要是衣物照片）
- UNKNOWN（如果無法判斷或兩者都有）"""

            # 調用 Gemini Vision API
            response = self.model.generate_content([prompt, img])
            
            if response and response.text:
                result = response.text.strip().upper()
                logger.info(f"📊 Gemini 分類結果: {result}")
                
                if "FACE" in result:
                    return "face"
                elif "CLOTHING" in result:
                    return "clothing"
                else:
                    return "unknown"
            else:
                logger.warning("⚠️ Gemini 返回空結果")
                return "unknown"
                
        except Exception as e:
            logger.error(f"❌ 圖片分類失敗: {e}", exc_info=True)
            return "unknown"
    
    def classify_images(self, images_base64: List[str]) -> Dict[str, List[str]]:
        """
        批次分類多張圖片
        
        Args:
            images_base64: Base64 編碼的圖片列表
            
        Returns:
            {
                "face_images": [...],      # 臉部照片列表
                "clothing_images": [...],  # 衣物照片列表
                "unknown_images": [...]    # 無法判斷的圖片
            }
        """
        result = {
            "face_images": [],
            "clothing_images": [],
            "unknown_images": []
        }
        
        for idx, img_base64 in enumerate(images_base64):
            logger.info(f"🔍 開始分類圖片 {idx + 1}/{len(images_base64)}")
            
            classification = self.classify_image(img_base64)
            
            if classification == "face":
                result["face_images"].append(img_base64)
                logger.info(f"   ✅ 圖片 {idx + 1}: 臉部照片")
            elif classification == "clothing":
                result["clothing_images"].append(img_base64)
                logger.info(f"   ✅ 圖片 {idx + 1}: 衣物照片")
            else:
                result["unknown_images"].append(img_base64)
                logger.info(f"   ⚠️ 圖片 {idx + 1}: 無法判斷")
        
        logger.info(f"\n📊 分類統計:")
        logger.info(f"   臉部照片: {len(result['face_images'])} 張")
        logger.info(f"   衣物照片: {len(result['clothing_images'])} 張")
        logger.info(f"   無法判斷: {len(result['unknown_images'])} 張\n")
        
        return result

# 單例模式
image_classifier = ImageClassifier()
