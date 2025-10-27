from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from pathlib import Path
import os, logging, uuid, shutil, json
import re
from datetime import datetime
from typing import List, Optional

# --- 圖片處理套件 ---
from rembg import remove
from PIL import Image
from io import BytesIO
# --------------------

# --- 環境配置 (從您提供的程式碼中提取並簡化) ---
from dotenv import load_dotenv
import openai 
from app.core.db import get_db
from app.models.wardrobe import WardrobeItem
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.services.storage import upload_file_to_gcs
from app.services.image_processing import gemini_classify_image
# --------------------

logging.basicConfig(level=logging.INFO)
router = APIRouter()

# --- 資料夾設定 ---
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

load_dotenv()

# 為了讓程式碼可執行，手動定義 CATEGORY_FOLDERS 和 CATEGORY_NORMALIZE
CATEGORY_FOLDERS = {
    "上衣": "uploads/上衣",
    "洋裝": "uploads/洋裝",
    "褲子": "uploads/下身", # 褲子屬於下身
    "裙子": "uploads/下身", # 裙子屬於下身
    "外套": "uploads/外套",
    "鞋子": "uploads/鞋子",
    "包包": "uploads/包包",
    "帽子": "uploads/帽子",
    "襪子": "uploads/襪子",
    "配件": "uploads/配件",
    "特殊": "uploads/特殊",
}

# 輔助：類別正規化字典
CATEGORY_NORMALIZE = {
    "上衣": "上衣",
    "洋裝": "洋裝",
    "褲子": "褲子",
    "裙子": "裙子",
    "外套": "外套",
    "鞋子": "鞋子",
    "包包": "包包",
    "帽子": "帽子",
    "襪子": "襪子",
    "配件": "配件",
    "下身": "褲子", 
}

for folder in CATEGORY_FOLDERS.values():
    Path(folder).mkdir(parents=True, exist_ok=True)

# 輔助函式：從 dict 中安全取出/移除指定 key (大小寫不敏感)
def _pop_like(d: dict, candidates: List[str]) -> str:
    """從字典中嘗試取出指定 key 的值，不區分大小寫，並移除該鍵"""
    if not isinstance(d, dict):
        return ""
    
    lower_map = {kk.lower(): kk for kk in d.keys()}
    
    for k in candidates:
        lk = k.lower()
        if lk in lower_map:
            original_k = lower_map[lk]
            v = d.pop(original_k)
            return str(v).strip() if v is not None else ""
            
    return ""

# 輔助函式：根據類別決定儲存路徑
def _get_dest_folder(category_val: str) -> Path:
    """根據類別值決定最終儲存的 Path 物件"""
    if category_val in CATEGORY_FOLDERS:
        return Path(CATEGORY_FOLDERS.get(category_val))
    
    # 針對多對一的分類進行處理
    if category_val in ["褲子", "裙子"]:
        return Path(CATEGORY_FOLDERS.get("褲子"))
    if category_val in ["洋裝", "上衣"]:
        return Path(CATEGORY_FOLDERS.get("上衣"))

    return UPLOAD_FOLDER

# --- 核心上傳端點 (upload_image) ---

@router.post("/")
async def upload_image(
    files: List[UploadFile] = File(None),    
    file: UploadFile = File(None),        
    category: str = Form(""),
    name: str = Form(""),
    color: str = Form(""),
    style: str = Form(""),
    tags: str = Form("[]"), 
    attributes: str = Form("{}"),    
    remove_bg: str = Form("0"), # 0 或 1，由前端勾選決定
    ai_detect: str = Form("1"), # 0 或 1，預設啟用 AI 辨識
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    import json
    import uuid as _uuid

    files_list = files or ([file] if file is not None else [])
    logging.info(f"upload called, files_count={len(files_list)}, remove_bg={remove_bg}, user={getattr(current_user, 'id', None)}")

    if not files_list:
        raise HTTPException(status_code=400, detail="請上傳至少一張圖片")

    # 參數解析與正規化
    try:
        tags_list = json.loads(tags) if tags else []
        attributes_dict = json.loads(attributes) if attributes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="tags/attributes 格式錯誤")

    if not isinstance(attributes_dict, dict): attributes_dict = {}
    if not isinstance(tags_list, list): tags_list = [str(tags_list)] if tags_list else []
    tags_list = [str(t) for t in tags_list if t is not None]

    try:
        user_id_val = _uuid.UUID(str(current_user.id))
    except Exception:
        user_id_val = current_user.id

    # 類別正規化
    allowed_categories = set(CATEGORY_FOLDERS.keys())
    category_val = CATEGORY_NORMALIZE.get(category.strip(), category.strip()) if isinstance(category, str) else ""
    if category_val not in allowed_categories:
         category_val = "上衣" 

    results = []
    
    for file_obj in files_list:
        # 1. 讀取上傳檔案內容
        # 必須將檔案游標重設到開頭，並讀取所有內容
        await file_obj.seek(0)
        contents = await file_obj.read()
        
        # 預設：使用原始副檔名，內容為原始內容
        orig_ext = Path(file_obj.filename).suffix or ".jpg"
        final_contents = contents
        
        # 檔案命名基礎
        raw_name_multi = (name or "").strip()
        if not raw_name_multi:
            raw_name_multi = Path(file_obj.filename).stem or "file"
        safe_stem_multi = re.sub(r"[^\w\u4e00-\u9fff\-\s]", "_", raw_name_multi)[:80].strip() or "file"
        
        # --- 2. 智慧去背與強制轉 PNG ---
        is_bg_removed = False
        try:
            do_remove = str(remove_bg).lower() in ("1", "true", "yes")
        except Exception:
            do_remove = False

        if do_remove:
            logging.info(f"對檔案 {file_obj.filename} 執行去背並強制轉為 PNG...")
            try:
                # 執行去背
                input_image = Image.open(BytesIO(contents))
                output_image = remove(input_image, alpha_matting=True)

                # 強制輸出為 PNG 格式並存入 BytesIO (記憶體緩衝區)
                output_buffer = BytesIO()
                output_image.save(output_buffer, format="PNG")

                # 更新內容和副檔名
                final_contents = output_buffer.getvalue()
                final_ext = ".png" # 強制轉換為 PNG
                is_bg_removed = True
            except Exception as e:
                logging.error(f"去背失敗，儲存原始檔案: {e}")
                # 失敗時回退到儲存原始檔案
                final_contents = contents
                final_ext = orig_ext
                is_bg_removed = False
        else:
            final_ext = orig_ext
        
        # --- 3. 儲存檔案 ---

        dest_folder = _get_dest_folder(category_val)
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        # 組合新的檔案名稱
        candidate = f"{safe_stem_multi}{final_ext}"
        fname = candidate
        save_path = dest_folder / fname
        
        # 若已存在同名檔案，加入時間戳避免覆蓋
        if save_path.exists():
            stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            fname = f"{safe_stem_multi}_{stamp}{final_ext}"
            save_path = dest_folder / fname

        try:
            with open(save_path, "wb") as buf:
                # 寫入處理後的內容
                buf.write(final_contents) 
        except Exception as e:
            logging.error(f"檔案儲存失敗: {e}")
            raise HTTPException(status_code=400, detail="檔案儲存失敗")

        # --- 3.5 使用 Gemini 自動識別衣物屬性（如果 ai_detect 為 1） ---
        ai_detected_data = None
        color_val = color or ""  # 初始化顏色變數
        style_val = style or ""  # 初始化風格變數
        
        if str(ai_detect).lower() in ("1", "true", "yes"):
            try:
                logging.info(f"使用 Gemini 分析衣物: {save_path}")
                ai_detected_data = gemini_classify_image(str(save_path))
                logging.info(f"Gemini 分析結果: {ai_detected_data}")
                
                # 如果用戶未提供分類或分類為預設值，使用 AI 結果
                # 更新邏輯：優先使用 AI 辨識的結果
                if not category_val or category_val == "上衣" or category_val == "特殊":
                    ai_category = ai_detected_data.get("category", "特殊")
                    if ai_category and ai_category != "特殊":
                        category_val = ai_category
                        logging.info(f"✅ 使用 AI 辨識的類別: {category_val}")
                
                # 如果用戶未提供顏色，使用 AI 結果
                if not color_val:
                    colors = ai_detected_data.get("colors", [])
                    color_val = colors[0] if colors else ""
                    if color_val:
                        logging.info(f"✅ 使用 AI 辨識的顏色: {color_val}")
                
                # 將 AI 識別的結果存入 style
                if not style_val and ai_detected_data.get("style"):
                    style_val = ai_detected_data.get("style")
                    logging.info(f"✅ 使用 AI 辨識的風格: {style_val}")
                
                # 儲存完整的 AI 分析結果到 attributes
                ai_results = {
                    "ai_category": ai_detected_data.get("category"),
                    "ai_colors": ai_detected_data.get("colors", []),
                    "ai_style": ai_detected_data.get("style"),
                    "ai_material": ai_detected_data.get("material"),
                    "ai_occasion": ai_detected_data.get("occasion"),
                    "ai_size": ai_detected_data.get("size")
                }
                attributes_dict.update(ai_results)
                
            except Exception as e:
                logging.warning(f"Gemini 分析失敗，使用手動輸入值: {e}")
                # 即使分析失敗，也要繼續進行

        # --- 4. 準備 DB 寫入資料 ---
        
        try:
            # 必須複製 attributes_dict，因為 _pop_like 會修改它
            current_attributes_dict = attributes_dict.copy()
            
            # 從 attributes 與 tags 拆出 brand / style
            brand_val = _pop_like(current_attributes_dict, ["brand", "Brand", "品牌"]) or ""
            style_val = _pop_like(current_attributes_dict, ["style", "Style", "風格", "款式"]) or ""

            # ... ( style 補充邏輯與原程式碼相同，略)

            # --- 關鍵變更：將去背狀態寫入 attributes 字典 ---
            current_attributes_dict["bg_removed"] = is_bg_removed
            # -----------------------------------------------------

            # cover image url
            cover_rel_path = f"{dest_folder.as_posix()}/{fname}"
            cover_url = f"/{cover_rel_path.lstrip('/')}"
            
            # 取得模型欄位清單
            try:
                 model_cols = set(c.name for c in WardrobeItem.__table__.columns)
            except Exception:
                 model_cols = set()

            item_kwargs = {}
            if "user_id" in model_cols: item_kwargs["user_id"] = user_id_val
            if "category" in model_cols: item_kwargs["category"] = category_val
            if "name" in model_cols: item_kwargs["name"] = name or ""
            if "cover_image_url" in model_cols: item_kwargs["cover_image_url"] = cover_url
            elif "cover_img_url" in model_cols: item_kwargs["cover_img_url"] = cover_url
            if "color" in model_cols: item_kwargs["color"] = color_val  # 使用 AI 辨識後的顏色
            if "tags" in model_cols: item_kwargs["tags"] = tags_list
            # 寫入包含去背狀態的 attributes
            if "attributes" in model_cols: item_kwargs["attributes"] = current_attributes_dict 
            if "brand" in model_cols: item_kwargs["brand"] = brand_val
            # Avoid inserting empty string into ENUM columns (Postgres will reject "")
            if "style" in model_cols and style_val:
                item_kwargs["style"] = style_val
            
            # 建立 WardrobeItem 實體並儲存
            item = WardrobeItem(**item_kwargs)
            db.add(item)
            db.commit()
            db.refresh(item)

            result_item = {
                "original_filename": file_obj.filename,
                "stored_path": cover_rel_path,
                "db_id": item.id,
                "category": category_val,  # AI 辨識後的類別
                "name": name,
                "brand": brand_val,
                "color": color_val,  # AI 辨識後的顏色
                "style": style_val,  # AI 辨識後的風格
                "cover_url": cover_url,
                "bg_removed": is_bg_removed # 回傳去背狀態給前端
            }
            
            # 如果有 AI 分析結果，也回傳給前端
            if ai_detected_data:
                result_item["ai_analysis"] = ai_detected_data
            
            results.append(result_item)

        except Exception as e:
            logging.error(f"DB 寫入失敗或資料處理失敗: {e}")
            # 寫入失敗時，刪除已儲存的檔案並回滾 DB
            try:
                save_path.unlink(missing_ok=True)
            except Exception:
                pass
            db.rollback()
            raise HTTPException(status_code=500, detail=f"資料儲存失敗: {e}")

    return {"message": f"成功處理 {len(results)} 張圖片", "results": results}


# 為衣服上傳新增別名路由
@router.post("/clothes")
async def upload_clothes(
    files: List[UploadFile] = File(None),    
    file: UploadFile = File(None),        
    category: str = Form(""),
    name: str = Form(""),
    color: str = Form(""),
    style: str = Form(""),
    tags: str = Form("[]"), 
    attributes: str = Form("{}"),    
    remove_bg: str = Form("0"),
    ai_detect: str = Form("1"),  # 預設啟用 AI 辨識
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    衣服上傳別名路由，代理至 upload_image
    """
    return await upload_image(
        files=files,
        file=file,
        category=category,
        name=name,
        color=color,
        style=style,
        tags=tags,
        attributes=attributes,
        remove_bg=remove_bg,
        ai_detect=ai_detect,
        db=db,
        current_user=current_user
    )


# 為了兼容性，保留這個空的 upload_file 函式，或建議您將其移除。
@router.post("/upload_file", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form("上衣"),
    color: str = Form(""),
    style: str = Form(""),
    tags: str = Form("[]"),
    attributes: str = Form("{}"),
    remove_bg: str = Form("0"), # 0 或 1
    ai_detect: str = Form("1"),  # 預設啟用 AI 辨識
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 這裡可以呼叫 upload_image 進行實際處理，或者簡單地返回一個錯誤，
    # 由於您提供了兩個同路徑但不同參數的 post 函式，我們假設您應當統一使用 upload_image。
    # 這裡將其簡化為錯誤提示，強制使用 files 參數：
    raise HTTPException(status_code=400, detail="請使用 / 路由並以 files 參數上傳。")


# ===== 新增：AI 衣物分析端點 =====
@router.post("/analyze-clothing")
async def analyze_clothing_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    直接使用 Gemini AI 分析上傳的衣物圖片
    返回衣物類別、顏色、材質、風格等信息
    不需要完整的上傳流程，只進行分析
    
    參數：
    - file: 衣物圖片文件
    
    返回：
    {
        "category": "衣物類別",
        "colors": ["顏色1", "顏色2"],
        "style": "風格",
        "material": "材質",
        "occasion": "場合",
        "size": "尺寸"
    }
    """
    try:
        # 讀取上傳的檔案到臨時位置
        temp_dir = Path("temp_analysis")
        temp_dir.mkdir(exist_ok=True)
        
        temp_filename = f"temp_{uuid.uuid4().hex}{Path(file.filename).suffix}"
        temp_path = temp_dir / temp_filename
        
        # 寫入臨時檔案
        contents = await file.read()
        with open(temp_path, "wb") as f:
            f.write(contents)
        
        try:
            # 調用 Gemini 分析
            analysis_result = gemini_classify_image(str(temp_path))
            logging.info(f"衣物分析完成: {analysis_result}")
            
            return {
                "success": True,
                "analysis": analysis_result
            }
        
        finally:
            # 刪除臨時檔案
            try:
                temp_path.unlink(missing_ok=True)
            except Exception as e:
                logging.warning(f"刪除臨時檔案失敗: {e}")
    
    except Exception as e:
        logging.error(f"衣物分析失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"衣物分析失敗: {str(e)}"
        )