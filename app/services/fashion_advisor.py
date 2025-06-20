# app/services/fashion_advisor.py
from dotenv import load_dotenv
import os
import logging
from typing import Optional, Dict, Any, List
from app.core.config import settings
from openai import AsyncOpenAI
import json
import openai
# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logging.error("未設定 OPENAI_API_KEY 環境變數！")
openai.api_key = OPENAI_API_KEY


class FashionAdvisor:
    def __init__(self, wardrobe_root: str = "wardrobe"):
        self.wardrobe_root = wardrobe_root
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def get_wardrobe_items(self) -> Dict[str, List[str]]:
        """讀取衣櫃中的衣物圖片路徑，依分類整理。"""
        wardrobe = {}
        if not os.path.exists(self.wardrobe_root):
            logging.warning("找不到衣櫥資料夾")
            return wardrobe

        for category in os.listdir(self.wardrobe_root):
            category_path = os.path.join(self.wardrobe_root, category)
            if os.path.isdir(category_path):
                wardrobe[category] = [
                    os.path.join(category_path, f)
                    for f in os.listdir(category_path)
                    if f.endswith(('.png', '.jpg', '.jpeg', '.webp'))
                ]
        return wardrobe

    def build_prompt_from_free_text(self, user_input: str, wardrobe: Dict[str, List[str]]) -> str:
        flat_items = []
        for category, items in wardrobe.items():
            flat_items.extend([f"{category}: {os.path.basename(path)}" for path in items])

        items_str = "\n".join(flat_items)

        prompt = f"""
你是一位專業的時尚穿搭師，幫使用者根據他的敘述推薦穿搭。
以下是使用者的衣櫃清單，每件衣服都已經去背，可以任意搭配使用：

{items_str}

使用者說：「{user_input}」

請根據使用者的需求與語境，自行推斷場合、溫度、活動類型、需求，並從衣櫥中挑選出一套合適的穿搭。

請只回傳以下 JSON 格式，不需要多餘解釋文字，例如：
```json
{{
  "上衣": "xxx.png",
  "下身": "yyy.webp",
  "鞋子": "zzz.png",
  "外套": "aaa.jpg",
  "配件": "bbb.png"
}}
如果不需要外套或配件，請填入 null。
"""
        return prompt

    async def get_outfit_advice_from_free_text(self, user_input: str) -> Dict[str, Any]:
        wardrobe = self.get_wardrobe_items()
        if not wardrobe:
            return {"error": "衣櫃為空"}

        prompt = self.build_prompt_from_free_text(user_input, wardrobe)

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            answer = response.choices[0].message.content.strip()
            return {"prompt": prompt, "recommendation": answer}

        except Exception as e:
            logging.error(f"OpenAI API 發生錯誤：{e}")
            return {"error": f"OpenAI API 發生錯誤：{str(e)}"}