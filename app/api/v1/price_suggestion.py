#app/api/v1/price_suggestion.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.image_processing import compress_image_for_gpt
from app.services.fashion_advisor import FashionAdvisor  # 導入 FashionAdvisor
import openai
import logging
import os
from typing import Optional

router = APIRouter()

# 載入 OpenAI API 金鑰 - 使用新版本 OpenAI 客戶端
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logging.error("未設定 OPENAI_API_KEY 環境變數！")
    client = None
else:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

# 初始化 FashionAdvisor
fashion_advisor = FashionAdvisor()

@router.get("/wardrobe-items")
async def get_wardrobe_items():
    """
    獲取所有衣櫃中的衣物圖片，依分類顯示
    """
    try:
        wardrobe_items = fashion_advisor.get_wardrobe_items()
        
        # 轉換為更適合前端顯示的格式
        formatted_items = {}
        for category, items in wardrobe_items.items():
            formatted_items[category] = []
            for item_path in items:
                formatted_items[category].append({
                    "filename": os.path.basename(item_path),
                    "path": item_path,
                    "url": f"/{item_path}",  # 提供URL供前端顯示
                })
        
        return {
            "message": "成功獲取衣櫃物品",
            "wardrobe_items": formatted_items
        }
    
    except Exception as e:
        logging.error(f"獲取衣櫃物品失敗: {str(e)}")
        raise HTTPException(status_code=500, detail="無法獲取衣櫃物品")

@router.post("/")
async def suggest_price(
    condition_percentage: int = Form(...),
    original_value: str = Form(...),
    file: Optional[UploadFile] = File(None),  # 可選的新上傳檔案
    existing_image_path: Optional[str] = Form(None),  # 已存在的圖片路徑
):
    """
    接收客戶上傳的圖片或選擇已存在的圖片，並根據使用時間和破損程度生成建議售價。
    """
    try:
        if not client:
            raise HTTPException(status_code=500, detail="OpenAI API 未正確設定")
        
        # 確保上傳目錄存在
        os.makedirs("uploaded_images", exist_ok=True)
        
        # 決定使用哪個圖片
        if file:
            # 使用新上傳的檔案
            file_location = f"uploaded_images/{file.filename}"
            with open(file_location, "wb") as buffer:
                buffer.write(await file.read())
        elif existing_image_path:
            # 使用已存在的檔案
            file_location = existing_image_path
            if not os.path.exists(file_location):
                raise HTTPException(status_code=404, detail="指定的圖片檔案不存在")
        else:
            raise HTTPException(status_code=400, detail="請提供圖片檔案或指定已存在的圖片路徑")

        # 壓縮圖片並轉換為 base64
        base64_image = compress_image_for_gpt(file_location)

        # GPT 分析邏輯 - 使用新版本 API，強制要求 JSON 格式
        prompt = f"""
你是一位專業的二手衣物估價師，請根據圖片和以下資訊生成建議售價：
- 新舊程度：{condition_percentage}%（數字越高越新）
- 原始價格：{original_value}

請仔細觀察圖片中的衣物，評估其材質、品牌、款式和實際狀況。

**重要：請務必回傳標準 JSON 格式，不要有額外文字：**
{{"suggested_price": "NT$ XXX", "explanation": "簡短估價理由"}}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "你是專業的二手衣物估價師。請根據圖片分析衣物並給出準確估價，回應必須是純 JSON 格式。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=200,
            response_format={"type": "json_object"}  # 強制 JSON 格式
        )

        content = response.choices[0].message.content.strip()
        
        # 解析 JSON 回應
        try:
            import json
            result = json.loads(content)
        except json.JSONDecodeError:
            # 如果解析失敗，嘗試提取 JSON 部分
            import re
            json_match = re.search(r'\{[^}]*\}', content)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except:
                    result = {"suggested_price": "解析失敗", "explanation": content}
            else:
                result = {"suggested_price": "解析失敗", "explanation": content}
        
        return {"message": "估價完成", "result": result}

    except HTTPException:
        # 重新拋出 HTTP 異常
        raise
    except Exception as e:
        logging.error(f"估價失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"估價失敗: {str(e)}")

# 移除原來的 list-images endpoint，因為已經被 wardrobe-items 取代