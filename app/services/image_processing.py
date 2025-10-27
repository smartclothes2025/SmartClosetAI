from rembg import remove
from PIL import Image
import io
import logging
import base64
from pathlib import Path
import os
import re
import json

import vertexai
from vertexai.generative_models import GenerativeModel, Part

# 配置 Vertex AI
gcp_project_id = os.getenv("GCP_PROJECT_ID")
gcp_location = os.getenv("GCP_LOCATION", "us-central1")

if gcp_project_id and gcp_location:
    try:
        vertexai.init(project=gcp_project_id, location=gcp_location)
        logging.info("Vertex AI 初始化成功")
    except Exception as e:
        logging.warning(f"Vertex AI 初始化失敗: {e}，Gemini 功能將不可用")
else:
    logging.warning("GCP_PROJECT_ID 或 GCP_LOCATION 未設定，Gemini 功能將不可用")

def compress_image_for_gpt(image_path):
    img = Image.open(image_path)
    img = img.convert("RGB")
    img = img.resize((512, 512))  # 改成 512x512，讓 GPT 能看清楚細節
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)  # 提高品質到 85%
    img_bytes = buffer.getvalue()
    base64_str = base64.b64encode(img_bytes).decode("utf-8")
    return base64_str

def compress_image_for_gemini(image_path):
    """壓縮圖片並轉換為 base64，用於 Gemini API"""
    img = Image.open(image_path)
    img = img.convert("RGB")
    img = img.resize((512, 512))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    img_bytes = buffer.getvalue()
    base64_str = base64.b64encode(img_bytes).decode("utf-8")
    return base64_str

def process_image(image_path: str, ):
    try:
        with open(image_path, "rb") as f:
            input_bytes = f.read()
        output_bytes = remove(input_bytes)
        output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

        # 強制轉成 .png 檔名，並回傳絕對路徑
        src = Path(image_path)
        output_path = src.with_name(src.stem + "_processed.png")
        output_image.save(str(output_path))  # 會自動用 png 格式儲存
        return {"processed_image_path": str(output_path.resolve())}
    except Exception as e:
        logging.exception(f"process_image failed for {image_path}: {e}")
        # 讓呼叫端知道發生錯誤
        raise


def gemini_classify_image(image_path: str) -> dict:
    """
    使用 Gemini 分析衣物，回傳 JSON：
    category, colors, style, material, occasion, size
    """
    try:
        if not os.getenv("GEMINI_API_KEY"):
            logging.warning("Gemini API Key 未設定，使用默認值")
            return get_default_classification()
        
        base64_image = compress_image_for_gemini(image_path)

        # 使用正確的 Gemini API 方法
        model = GenerativeModel("gemini-2.5-flash")
        
        prompt = """請分析以下衣物圖片，並回傳 JSON 格式的結果。

返回格式必須為以下 JSON（不要有其他文字）：
{
  "category": "衣物類別",
  "colors": ["顏色1", "顏色2"],
  "style": "衣物風格",
  "material": "材質",
  "occasion": "場合",
  "size": "尺寸估計"
}

類別選項（必選其一）：
- 上衣（T恤、襯衫、毛衣等）
- 褲子（牛仔褲、長褲、短褲等）
- 裙子
- 外套（夾克、大衣等）
- 洋裝（連身裙）
- 鞋子
- 包包
- 帽子
- 襪子
- 飾品
- 特殊

顏色選項：黑、白、灰、紅、粉、橘、黃、綠、藍、紫、棕、米、其他

風格選項：簡約、甜美、韓系、美式休閒、街頭、復古、知性優雅、酷帥中性、運動、其他

材質選項：棉、麻、絲、羊毛、皮革、牛仔、合成纖維、混紡、其他

場合選項：上班、約會、運動、正式、學校、旅遊、居家、聚會、其他

尺寸選項：XS、S、M、L、XL、其他

必須**只返回 JSON，不要任何其他文字**。"""

        response = model.generate_content([
            {
                "mime_type": "image/jpeg",
                "data": base64_image
            },
            prompt
        ])
        
        # 正確處理回應
        content = response.text if hasattr(response, 'text') else str(response)
        logging.info(f"Gemini 回覆: {content}")
        
        # 嘗試提取 JSON
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                # 確保欄位完整
                result = {
                    "category": result.get("category", "特殊"),
                    "colors": result.get("colors", []) or [],
                    "style": result.get("style", ""),
                    "material": result.get("material", ""),
                    "occasion": result.get("occasion", ""),
                    "size": result.get("size", "")
                }
                return result
            except json.JSONDecodeError as e:
                logging.error(f"JSON 解析失敗: {e}，內容: {json_match.group()}")
                return get_default_classification()
        else:
            logging.error(f"無法找到 JSON 格式，原始內容: {content}")
            return get_default_classification()

    except Exception as e:
        logging.error(f"Gemini 分類失敗: {e}", exc_info=True)
        return get_default_classification()


def get_default_classification() -> dict:
    """當 Gemini 失敗時的默認分類"""
    return {
        "category": "特殊",
        "colors": [],
        "style": "",
        "material": "",
        "occasion": "",
        "size": ""
    }

# 直接替換原本分析函式
def analyze_clothing_type(image_path: str) -> dict:
    return gemini_classify_image(image_path)