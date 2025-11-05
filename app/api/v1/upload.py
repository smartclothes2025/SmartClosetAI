# app/api/v1/upload.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from pathlib import Path
import logging, re
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote # 用於 URL 編碼

# 圖片處理
from rembg import remove
from PIL import Image
from io import BytesIO

# 環境 / 專案相依
from dotenv import load_dotenv
from app.core.db import get_db
from app.models.wardrobe import WardrobeItem
from app.models.auth import User
from app.api.v1.auth import get_current_user

# 若專案有 GCS/storage 服務，可保留；沒有也不影響這支檔案執行
try:
    # 這裡引入了 generate_signed_url_from_gcs_uri
    from app.services.storage import upload_file_to_gcs_from_bytes, generate_signed_url_from_gcs_uri
    HAS_GCS = True
except Exception:
    HAS_GCS = False
    # 🎯 修正點 1: 在 GCS 關閉時，讓 generate_signed_url_from_gcs_uri 傳回原始 URI（如果是本地路徑 /uploads/，前端可處理）
    def generate_signed_url_from_gcs_uri(gcs_uri):
        return gcs_uri # 原樣返回

# 若有 Gemini 分析服務就使用，沒有則略過（ai_detect 仍可設為 0 關閉）
try:
    from app.services.image_processing import gemini_classify_image  # type: ignore
    HAS_GEMINI = True
except Exception:
    HAS_GEMINI = False

load_dotenv()
logging.basicConfig(level=logging.INFO)
router = APIRouter()

# GCS 設定
import os
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "smartclothes_wardrobe")

# 類別映射（僅用於 GCS 路徑）
GCS_CATEGORY_MAP = {
    "tops": "tops",
    "dresses": "dresses",
    "pants": "bottoms",
    "skirts": "bottoms",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "bags": "bags",
    "hats": "hats",
    "socks": "socks",
    "accessories": "accessories",
    "special": "special",
}

# 前端英文值到資料庫中文值的映射
CATEGORY_NORMALIZE = {
    "tops": "上衣",
    "dresses": "洋裝",
    "pants": "褲子",
    "skirts": "裙子",
    "outerwear": "外套",
    "shoes": "鞋子",
    "bags": "包包",
    "hats": "帽子",
    "socks": "襪子",
    "accessories": "配件",
    "bottoms": "褲子",  # 以褲子作為下身的主分類
    # 已經是中文的直接通過
    "上衣": "上衣",
    "裙子": "裙子",
    "褲子": "褲子",
    "洋裝": "洋裝",
    "外套": "外套",
    "鞋子": "鞋子",
    "帽子": "帽子",
    "包包": "包包",
    "配件": "配件",
}


def _pop_like(d: dict, candidates: List[str]) -> str:
    """從字典移除/取出候選 key（大小寫不敏感）。沒取到回空字串。"""
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
    remove_bg: str = Form("0"),    # "1" 開啟去背
    ai_detect: str = Form("1"),    # "1" 開啟 AI 辨識（若 HAS_GEMINI=False，會自動略過）
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上傳 1~N 張衣服圖片。
    - 去背（rembg）
    - 依分類寫入 uploads/對應資料夾
    - 寫入 WardrobeItem（含 attributes['bg_removed']）
    - 可選：Gemini 影像分析（顏色/風格/類別建議…）
    備註：此路由實際路徑會是 /api/v1/upload/（由外層 router prefix）
    """
    import json
    import uuid as _uuid

    files_list = files or ([file] if file is not None else [])
    logging.info(
        f"[upload] files_count={len(files_list)}, remove_bg={remove_bg}, ai_detect={ai_detect}, user={getattr(current_user, 'id', None)}"
    )

    if not files_list:
        raise HTTPException(status_code=400, detail="請上傳至少一張圖片")

    # 參數解析
    try:
        tags_list = json.loads(tags) if tags else []
        attributes_dict = json.loads(attributes) if attributes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="tags/attributes 格式錯誤")

    if not isinstance(attributes_dict, dict):
        attributes_dict = {}
    if not isinstance(tags_list, list):
        tags_list = [str(tags_list)] if tags_list else []
    tags_list = [str(t) for t in tags_list if t is not None]

    # 類別正規化
    # 先取得英文 category 用於 GCS 路徑
    category_input = category.strip() if isinstance(category, str) else ""
    allowed_categories = set(GCS_CATEGORY_MAP.keys())
    
    # 如果輸入是中文，先反向查找對應的英文 key
    category_en = category_input
    if category_input not in allowed_categories:
        # 嘗試從 CATEGORY_NORMALIZE 的值反向查找 key
        for k, v in CATEGORY_NORMALIZE.items():
            if v == category_input and k in allowed_categories:
                category_en = k
                break
    
    if category_en not in allowed_categories:
        category_en = "tops"
    
    # 轉換為資料庫使用的 GCS 路徑類別 (可能是 bottoms 而非 pants/skirts)
    category_gcs = GCS_CATEGORY_MAP.get(category_en, "tops")
    
    # 轉換為中文用於資料庫
    category_db = CATEGORY_NORMALIZE.get(category_en, "上衣")

    results = []
    
    # 這裡確保 user_id_str 可以在 GCS 上傳時被使用
    user_id_str = str(getattr(current_user, 'id', 'unknown'))

    for file_obj in files_list:
        # 讀檔
        await file_obj.seek(0)
        contents = await file_obj.read()
        orig_ext = Path(file_obj.filename).suffix or ".jpg"
        final_contents = contents

        # 檔名處理：優先使用者輸入的 name，否則使用原始檔名
        user_input_name = (name or "").strip()
        original_stem = Path(file_obj.filename).stem or ""
        
        # 決定使用哪個名稱
        if user_input_name:
            # 使用者有輸入名稱，使用它
            final_stem = user_input_name.replace(" ", "_")
        else:
            # 沒有輸入，使用原始檔名
            final_stem = original_stem.replace(" ", "_") if original_stem else "untitled"
        
        # 確保檔名不為空
        final_stem = final_stem.strip() or "untitled"
        
        logging.info(f"[upload] 使用者輸入名稱: {user_input_name}")
        logging.info(f"[upload] 原始檔名: {original_stem}")
        logging.info(f"[upload] 最終檔名: {final_stem}")  
                
        # 去背（PNG）
        is_bg_removed = False
        final_ext = orig_ext
        try:
            do_remove = str(remove_bg).lower() in ("1", "true", "yes")
        except Exception:
            do_remove = False

        if do_remove:
            try:
                input_image = Image.open(BytesIO(contents))
                output_image = remove(input_image, alpha_matting=True)
                out_buf = BytesIO()
                output_image.save(out_buf, format="PNG")
                final_contents = out_buf.getvalue()
                final_ext = ".png"
                is_bg_removed = True
            except Exception as e:
                logging.warning(f"[upload] 去背失敗，改存原檔：{e}")
                final_contents = contents
                final_ext = orig_ext
                is_bg_removed = False

        # ✅ 生成檔名並處理重複：如果遇到相同檔名，加上 _1, _2, ...
        base_filename = f"{final_stem}{final_ext}"
        unique_filename = base_filename
        
        # 上傳到 GCS（必須啟用，不允許本地上傳）
        gcs_uri = None # gs:// 格式，用於 DB 儲存
        gcs_signed_url = None # http(s):// 格式，用於 API 返回
        
        if not HAS_GCS:
            raise HTTPException(status_code=500, detail="GCS 服務未啟用，無法上傳圖片")
        
        # ✅ 檢查檔案是否存在，如果存在就加上數字後綴
        # 路徑格式: wardrobe/user_id/tops/檔名.jpg
        user_folder = f"wardrobe/{user_id_str}/{category_gcs}"
        base_gcs_path = f"{user_folder}/{base_filename}"
        gcs_blob_path = base_gcs_path
        
        logging.info(f"[upload] 📁 GCS 路徑將為: gs://{GCS_BUCKET_NAME}/{gcs_blob_path}")
        
        try:
            from google.cloud import storage as gcs_storage
            client = gcs_storage.Client()
            bucket = client.bucket(GCS_BUCKET_NAME)
            
            counter = 1
            while bucket.blob(gcs_blob_path).exists():
                # 分離檔名和副檔名
                stem_only = final_stem
                unique_filename = f"{stem_only}_{counter}{final_ext}"
                gcs_blob_path = f"{user_folder}/{unique_filename}"
                counter += 1
                if counter > 100:  # 安全上限
                    logging.warning(f"[upload] 檔名重複次數過多，使用時間戳: {final_stem}")
                    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                    unique_filename = f"{stem_only}_{timestamp}{final_ext}"
                    gcs_blob_path = f"{user_folder}/{unique_filename}"
                    break
            
            if counter > 1:
                logging.info(f"[upload] 檔名重複，使用: {unique_filename}")
        except Exception as e:
            logging.warning(f"[upload] 無法檢查檔案是否存在，使用原始檔名: {e}")
            gcs_blob_path = base_gcs_path
        
        # 決定 MIME type
        if final_ext.lower() == ".png":
            mime_type = "image/png"
        elif final_ext.lower() in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        else:
            mime_type = "image/jpeg"
        
        try:
            logging.info(f"[upload] 🚀 上傳到 GCS: {gcs_blob_path} (Bucket: {GCS_BUCKET_NAME})")
            
            # 上傳到 GCS
            gcs_uri = upload_file_to_gcs_from_bytes(
                file_bytes=final_contents,
                destination_blob_name=gcs_blob_path,
                mime_type=mime_type,
                bucket_name=GCS_BUCKET_NAME,
                public=False
            )
            logging.info(f"[upload] ✅ GCS 上傳成功：{gcs_uri}")
            
            # 生成簽名 URL
            gcs_signed_url = generate_signed_url_from_gcs_uri(gcs_uri)
            logging.info(f"[upload] 🔑 成功生成 GCS 簽名 URL: {gcs_signed_url}")
            
        except Exception as e:
            logging.error(f"[upload] ❌ GCS 上傳失敗：{e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"圖片上傳到 GCS 失敗: {str(e)}")

        # AI 分析（可選）
        ai_detected_data = None
        color_val = color or ""
        style_val = style or ""
        local_category = category_db  # 使用中文 category（可能由 AI 建議覆蓋）

        if str(ai_detect).lower() in ("1", "true", "yes") and HAS_GEMINI:
            try:
                # 為 AI 分析創建臨時檔案
                import uuid as _uuid_ai
                temp_dir = Path("temp_analysis")
                temp_dir.mkdir(exist_ok=True)
                temp_file = temp_dir / f"ai_{_uuid_ai.uuid4().hex}{final_ext}"
                with open(temp_file, "wb") as f:
                    f.write(final_contents)
                
                try:
                    ai_detected_data = gemini_classify_image(str(temp_file))
                    # ... (略過 AI 建議覆蓋邏輯) ...
                    ai_cat = (ai_detected_data or {}).get("category")
                    if ai_cat and (local_category in {"tops", "special"}):
                         local_category = ai_cat
                    if not color_val:
                         colors = (ai_detected_data or {}).get("colors", [])
                         color_val = colors[0] if colors else ""
                    if not style_val:
                         style_val = (ai_detected_data or {}).get("style") or ""
                finally:
                    # 清理臨時檔案
                    try:
                        temp_file.unlink(missing_ok=True)
                    except Exception as e:
                        logging.warning(f"[upload] 刪除臨時 AI 分析檔案失敗：{e}")

            except Exception as e:
                logging.warning(f"[upload] Gemini 分析失敗，忽略 AI：{e}")

        # 寫 DB
        try:
            # 拆出 brand/style（若 attributes 已含，避免重複）
            current_attr = attributes_dict.copy()
            brand_val = _pop_like(current_attr, ["brand", "Brand", "品牌"]) or ""
            style_from_attr = _pop_like(current_attr, ["style", "Style", "風格", "款式"]) or ""
            if not style_val:
                style_val = style_from_attr

            # 附帶狀態
            current_attr["bg_removed"] = is_bg_removed
            if ai_detected_data:
                 current_attr.update({
                    "ai_category": ai_detected_data.get("category"),
                    "ai_colors": ai_detected_data.get("colors", []),
                    "ai_style": ai_detected_data.get("style"),
                    "ai_material": ai_detected_data.get("material"),
                    "ai_occasion": ai_detected_data.get("occasion"),
                    "ai_size": ai_detected_data.get("size"),
                 })
            
            # DB 儲存 GCS URI，API 返回簽名 URL
            cover_url_db_final = gcs_uri
            cover_url_api_final = gcs_signed_url

            # 記錄上傳資訊
            logging.info(f"[UPLOAD] DB 儲存的 cover_image_url: {cover_url_db_final}")
            logging.info(f"[UPLOAD] 返回給前端的 cover_url: {cover_url_api_final}")

            try:
                model_cols = set(c.name for c in WardrobeItem.__table__.columns)
            except Exception:
                model_cols = set()

            item_kwargs = {}
            # ... (略過 user_id 處理) ...
            try:
                import uuid as _uuid
                user_id_val = _uuid.UUID(str(current_user.id))
            except Exception:
                user_id_val = current_user.id

            if "user_id" in model_cols:
                item_kwargs["user_id"] = user_id_val
            if "category" in model_cols:
                item_kwargs["category"] = local_category
            if "name" in model_cols:
                item_kwargs["name"] = name or ""
            
            # 🎯 修正點 2-D: DB 寫入使用 cover_url_db_final
            if "cover_image_url" in model_cols:
                item_kwargs["cover_image_url"] = cover_url_db_final 
            elif "cover_img_url" in model_cols:
                item_kwargs["cover_img_url"] = cover_url_db_final
                
            if "color" in model_cols:
                item_kwargs["color"] = color_val
            if "tags" in model_cols:
                item_kwargs["tags"] = tags_list
            if "attributes" in model_cols:
                item_kwargs["attributes"] = current_attr
            if "brand" in model_cols:
                item_kwargs["brand"] = brand_val
            if "style" in model_cols and style_val:
                item_kwargs["style"] = style_val
            
            # 設定 last_worn_at 為上傳時間
            if "last_worn_at" in model_cols:
                item_kwargs["last_worn_at"] = datetime.utcnow()

            item = WardrobeItem(**item_kwargs)
            db.add(item)
            db.commit()
            db.refresh(item)

            result = {
                "original_filename": file_obj.filename,
                "stored_path": gcs_blob_path,
                "db_id": item.id,
                "category": local_category,
                "name": name,
                "brand": brand_val,
                "color": color_val,
                "style": style_val,
                "cover_url": cover_url_api_final, 
                "bg_removed": is_bg_removed,
                "gcs_uri": gcs_uri,
            }
            if ai_detected_data:
                result["ai_analysis"] = ai_detected_data

            results.append(result)

        except Exception as e:
            logging.error(f"[upload] DB 寫入失敗：{e}", exc_info=True)
            db.rollback()
            raise HTTPException(status_code=500, detail=f"資料儲存失敗: {e}")

    return {"message": f"成功處理 {len(results)} 張圖片", "results": results}


@router.post("/clothes")
async def upload_clothes_alias(
    files: List[UploadFile] = File(None),
    file: UploadFile = File(None),
    category: str = Form(""),
    name: str = Form(""),
    color: str = Form(""),
    style: str = Form(""),
    tags: str = Form("[]"),
    attributes: str = Form("{}"),
    remove_bg: str = Form("0"),
    ai_detect: str = Form("1"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """別名路由，與 POST / 相同。"""
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
        current_user=current_user,
    )


@router.post("/upload_file", status_code=201)
async def upload_file_legacy(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form("tops"),
    color: str = Form(""),
    style: str = Form(""),
    tags: str = Form("[]"),
    attributes: str = Form("{}"),
    remove_bg: str = Form("0"),
    ai_detect: str = Form("1"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """舊相容端點：提醒改用 / 並以 files 參數上傳。"""
    raise HTTPException(status_code=400, detail="請使用 POST /api/v1/upload/ 並以 files 參數上傳。")


@router.post("/analyze-clothing")
async def analyze_clothing_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    僅做 AI 影像分析（不存檔/不入庫）。
    回傳：category/colors/style/material/occasion/size（若服務可提供）。
    """
    import uuid as _uuid

    if not HAS_GEMINI:
        raise HTTPException(status_code=501, detail="伺服器未啟用 AI 影像分析服務")

    try:
        temp_dir = Path("temp_analysis")
        temp_dir.mkdir(exist_ok=True)
        tmp = temp_dir / f"tmp_{_uuid.uuid4().hex}{Path(file.filename).suffix}"

        content = await file.read()
        with open(tmp, "wb") as f:
            f.write(content)

        try:
            analysis = gemini_classify_image(str(tmp))
            return {"success": True, "analysis": analysis}
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception as e:
                logging.warning(f"[upload] 刪除臨時檔失敗：{e}")

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[upload] AI 分析失敗：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"衣物分析失敗: {str(e)}")