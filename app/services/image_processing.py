from rembg import remove
from PIL import Image
import io
import openai 
import logging
import base64

def compress_image_for_gpt(image_path):
    img = Image.open(image_path)
    img = img.convert("RGB")
    img = img.resize((512, 512))  # 改成 512x512，讓 GPT 能看清楚細節
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)  # 提高品質到 85%
    img_bytes = buffer.getvalue()
    base64_str = base64.b64encode(img_bytes).decode("utf-8")
    return base64_str

def process_image(image_path: str, ):
    with open(image_path, "rb") as f:
        input_bytes = f.read()
    output_bytes = remove(input_bytes)
    output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    # 強制轉成 .png 檔名
    output_path = (
        image_path.rsplit('.', 1)[0] + "_processed.png"
    )
    output_image.save(output_path)  # 會自動用 png 格式儲存
    return {
        "processed_image_path": output_path,
    }

import re
import json

def gpt_classify_image_from_file(image_path: str) -> dict:
    try:
        base64_image = compress_image_for_gpt(image_path)
        
        # 修正 prompt，使用正確的圖片格式
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "你是專業的服裝分類助手。請仔細觀察圖片中的衣物，準確分類。"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """請根據圖片中的衣物，回傳JSON格式：
{"category":"上衣/下身/外套/洋裝/鞋子/包包/帽子/襪子/飾品/特殊",
"colors":["紅","藍","綠","黃","黑","白","灰","橘","粉","紫"],
"occasion":["上班","約會","運動","正式","學校","旅遊","居家"],
"style":["簡約","甜美","韓系","美式休閒","街頭","復古","知性優雅","酷帥中性"]}

分類規則：
- 裙子 = 下身
- T恤、襯衫、毛衣 = 上衣  
- 牛仔褲、長褲、短褲 = 下身
- 連身裙 = 洋裝
- 外套、夾克 = 外套

請只回傳JSON，不要其他文字。"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        )
        
        content = response.choices[0].message.content.strip()
        
        # 用正則抽取第一個 JSON 物件（大括號內）
        json_match = re.search(r"\{.*?\}", content, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            result = json.loads(json_str)
            # 確保 colors 是 list，如果是字串轉成 list
            if isinstance(result.get("colors"), str):
                result["colors"] = [result["colors"]]
            # 基本欄位補強，避免缺欄位出錯
            result.setdefault("category", "特殊")
            result.setdefault("colors", [])
            result.setdefault("occasion", "")
            result.setdefault("style", "")
        else:
            logging.error(f"GPT 回覆非 JSON 格式，回覆內容: {content}")
            # 修改回覆，強制生成 JSON 格式
            result = {
                "category": "特殊",
                "colors": [],
                "occasion": "",
                "style": ""
            }
        return result
    except Exception as e:
        logging.error(f"GPT 圖像分類失敗: {e}")
        return {
            "category": "特殊",
            "colors": [],
            "occasion": "",
            "style": ""
        }

def analyze_clothing_type(image_path: str) -> str:
    """
    直接透過 GPT 分析圖片的衣物種類。
    """
    return gpt_classify_image_from_file(image_path)