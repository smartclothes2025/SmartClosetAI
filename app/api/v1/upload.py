#api/v1/upload.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from app.core.db import get_db 
from app.models.wardrobe import Wardrobe 
from app.models.auth import User 
from app.api.v1.auth import get_current_user 
import os, base64, openai, logging, uuid, shutil, json, re
from app.services.image_processing import process_image, analyze_clothing_type
from typing import List
from fastapi import UploadFile, File

logging.basicConfig(level=logging.INFO)

router = APIRouter()

# 儲存上傳圖片的資料夾
UPLOAD_FOLDER = Path("uploaded_images")

# 確保資料夾存在
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# 載入 .env 環境變數
load_dotenv()

# 載入 OpenAI API 金鑰
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
     logging.error("未設定 OPENAI_API_KEY 環境變數！")
     openai_client = None 
else:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 建立衣物類型資料夾
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

# 建立所有類型資料夾（只做一次）
for folder in CATEGORY_FOLDERS.values():
    Path(folder).mkdir(parents=True, exist_ok=True)

# 取出 category 欄位
def classify_to_folder(classify_result) -> str:
    # classify_result 是 dict
    category = classify_result.get("category", "")
    
    # 特殊處理牛仔褲和褲子
    if "pants" in category.lower() or "jeans" in category.lower() or "牛仔褲" in category:
        return CATEGORY_FOLDERS["下身"]
    
    # 其他類型的映射
    for keyword, folder in CATEGORY_FOLDERS.items():
        if keyword == category:
            return folder
    
    return CATEGORY_FOLDERS["特殊"]


@router.post("/")
async def upload_image(files: List[UploadFile] = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="請上傳至少一張圖片")
    
    results = []
    """
    上傳圖片 → 自動去背 → 分析類型 → 儲存到相對應類型的衣櫥
    """
    
    # 處理每一張圖片（統一處理流程）
    for file in files:
        filename = f"{uuid.uuid4()}{Path(file.filename).suffix}"
        file_location = UPLOAD_FOLDER / filename

        try:
            # 1. 儲存圖片到本地資料夾
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            logging.error(f"儲存檔案 {filename} 失敗: {e}")
            if file_location.exists():
                os.remove(file_location)
            # 單張圖片失敗時拋出異常，多張圖片時跳過
            if len(files) == 1:
                raise HTTPException(status_code=400, detail="無效的檔案或無法儲存檔案")
            continue

        try:
            # 2. 處理圖片（去背）
            result = process_image(str(file_location))
            processed_image_path = result["processed_image_path"]
        except Exception as e:
            logging.error(f"圖片處理失敗: {e}")
            # 清理臨時檔案
            if file_location.exists():
                os.remove(file_location)
            if len(files) == 1:
                raise HTTPException(status_code=500, detail="圖片處理失敗")
            continue

        try:
            # 3. 分析衣物類型與標籤（使用處理後的圖片）
            clothing_info = analyze_clothing_type(str(processed_image_path))
            if not isinstance(clothing_info, dict):
                raise ValueError("衣物分類結果不是有效的 JSON 格式")
        except Exception as e:
            logging.error(f"衣物分類失敗: {e}")
            # 清理臨時檔案
            if file_location.exists():
                os.remove(file_location)
            if Path(processed_image_path).exists():
                os.remove(processed_image_path)
            if len(files) == 1:
                raise HTTPException(status_code=500, detail="衣物分類失敗或回傳格式錯誤")
            continue

        try:
            # 4. 分類儲存路徑
            category_folder = classify_to_folder(clothing_info)
            final_path = Path(category_folder) / Path(processed_image_path).name
            shutil.move(processed_image_path, final_path)

            # 5. 儲存進資料庫
            db_item = Wardrobe(
                filename=final_path.name,
                category=clothing_info.get("category", "特殊"),
                color=json.dumps(clothing_info.get("colors", [])),
                style=json.dumps(clothing_info.get("style", [])),
                occasion=json.dumps(clothing_info.get("occasion", [])),
                user_id=current_user.id
            )
            db.add(db_item)
            db.commit()
            db.refresh(db_item)

            # 6. 添加到結果列表
            results.append({
                "original_filename": file.filename,
                "stored_filename": final_path.name,
                "processed_image_path": str(final_path),
                "clothing_info": clothing_info,
                "category_folder": category_folder
            })
            
            logging.info(f"成功處理圖片: {file.filename} -> {final_path}")

        except Exception as e:
            logging.error(f"資料庫寫入或檔案移動失敗: {e}")
            # 清理可能的檔案
            if file_location.exists():
                os.remove(file_location)
            if Path(processed_image_path).exists():
                os.remove(processed_image_path)
            if len(files) == 1:
                raise HTTPException(status_code=500, detail="資料庫寫入失敗")
            continue

        finally:
            # 清理原始上傳檔案
            if file_location.exists():
                os.remove(file_location)

    return {
        "message": f"成功處理 {len(results)} 張圖片",
        "results": results
    }