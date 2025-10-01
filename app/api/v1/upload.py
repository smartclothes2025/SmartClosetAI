# api/v1/upload.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import os, logging, uuid, shutil, json
from dotenv import load_dotenv
import openai

from app.core.db import get_db
from app.models.wardrobe import Wardrobe
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.services.image_processing import process_image, analyze_clothing_type
from typing import List

logging.basicConfig(level=logging.INFO)
router = APIRouter()

# 圖片暫存與資料夾
UPLOAD_FOLDER = Path("uploaded_images")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# 讀取 .env
load_dotenv()

# 設定 OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logging.error("未設定 OPENAI_API_KEY 環境變數！")
else:
    openai.api_key = OPENAI_API_KEY

# 衣物分類資料夾對應
CATEGORY_FOLDERS = {
    "上衣": "wardrobe/上衣",
    "下身": "wardrobe/下身",
    "外套": "wardrobe/外套",
    "洋裝": "wardrobe/洋裝",
    "鞋子": "wardrobe/鞋子",
    "包包": "wardrobe/包包",
    "帽子": "wardrobe/帽子",
    "襪子": "wardrobe/襪子",
    "飾品": "wardrobe/飾品",
    "特殊": "wardrobe/特殊",
}
for folder in CATEGORY_FOLDERS.values():
    Path(folder).mkdir(parents=True, exist_ok=True)

def classify_to_folder(info: dict) -> str:
    """根據分類結果決定存放資料夾"""
    cat = info.get("category", "")
    if any(k in cat.lower() for k in ["pants", "jeans", "牛仔褲"]):
        return CATEGORY_FOLDERS["下身"]
    return CATEGORY_FOLDERS.get(cat, CATEGORY_FOLDERS["特殊"])

@router.post("/")
async def upload_image(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not files:
        raise HTTPException(status_code=400, detail="請上傳至少一張圖片")
    results = []

    for file in files:
        # 1. 存檔
        ext = Path(file.filename).suffix
        fname = f"{uuid.uuid4()}{ext}"
        temp_path = UPLOAD_FOLDER / fname
        try:
            with open(temp_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
        except Exception as e:
            logging.error(f"儲存失敗: {e}")
            raise HTTPException(status_code=400, detail="檔案儲存失敗")

        # 2. 去背與影像處理
        try:
            proc = process_image(str(temp_path))
            processed_path = Path(proc["processed_image_path"])
        except Exception as e:
            logging.error(f"圖片處理失敗: {e}")
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="圖片處理失敗")

        # 3. AI 分析
        try:
            info = analyze_clothing_type(str(processed_path))
            if not isinstance(info, dict):
                raise ValueError("分類結果不是 dict")
        except Exception as e:
            logging.error(f"衣物分類失敗: {e}")
            temp_path.unlink(missing_ok=True)
            processed_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="衣物分類失敗")

        # 4. 分類儲存及 DB 寫入
        dest_dir = classify_to_folder(info)
        final_path = Path(dest_dir) / processed_path.name
        try:
            shutil.move(str(processed_path), str(final_path))
            item = Wardrobe(
                filename=final_path.name,
                category=info.get("category", "特殊"),
                color=json.dumps(info.get("colors", [])),
                style=json.dumps(info.get("style", [])),
                occasion=json.dumps(info.get("occasion", [])),
                user_id=current_user.id
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            results.append({
                "original": file.filename,
                "stored": final_path.name,
                "info": info
            })
        except Exception as e:
            logging.error(f"儲存或 DB 寫入失敗: {e}")
            final_path.unlink(missing_ok=True)
            temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="資料儲存失敗")
        finally:
            temp_path.unlink(missing_ok=True)

    return {"message": f"成功處理 {len(results)} 張圖片", "results": results}
