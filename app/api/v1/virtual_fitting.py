# app/api/v1/virtual_fitting.py
"""
Virtual Fitting API - AI-powered realistic try-on generation
Uses AI image generation services to create realistic clothing try-on images
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from typing import List, Optional
import os
import base64
from io import BytesIO
from PIL import Image
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone

# Import our image generation service
from app.services.image_generation import image_service
from app.core.db import get_db
from app.models.auth import User
from app.models.outfit import Outfit
from app.models.wardrobe import WardrobeItem
from app.services.storage import (
    upload_file_to_gcs_from_bytes,
    generate_signed_url_from_gcs_uri,
)

# Setup logger
logger = logging.getLogger(__name__)

# ============================================================
#  只從 Header 讀 token 的認證方法（避免跟 Form 衝突）
# ============================================================
def get_current_user_from_header(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    從 Header 的 Authorization: Bearer user-<uuid>-token 驗證使用者
    專用於 JSON body 端點，避免與 Form 參數衝突
    """
    from app.api.v1.auth import (
        AUTH_BEARER_PREFIX,
        ERR_INVALID_TOKEN,
        ERR_USER_NOT_FOUND,
    )
    import uuid as _uuid

    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        logger.warning("未收到 Authorization header，拒絕存取虛擬試衣 API")
    token = None

    if auth_header.startswith(AUTH_BEARER_PREFIX):
        token = auth_header.split(" ", 1)[1]

    if not token:
        logger.warning("Authorization header 格式錯誤或缺少 Bearer token")
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    user_id = token[len(prefix) : -len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    try:
        _uuid.UUID(user_id)
    except Exception:
        logger.warning("Authorization token 無法解析為有效 UUID")
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)
    logger.info(f"成功驗證使用者 {user_id}，可訪問虛擬試衣 API")
    return user


# ⚠️ 這裡不要再加 prefix="/fitting"
# 真正的 /fitting 是在 app/api/v1/router.py 裡面加的
router = APIRouter(tags=["fitting"])


# ============================================================
#  資料模型
# ============================================================
class ClothingItem(BaseModel):
    id: str  # 支援 UUID 字串或 int 轉成的 str
    name: str
    category: str
    img: Optional[str] = None


class VirtualFittingRequest(BaseModel):
    user_input: str
    selected_items: List[ClothingItem]
    user_photo: Optional[str] = None  # Base64 encoded user photo


class VirtualFittingResponse(BaseModel):
    type: str  # 'image' or 'text'
    url: Optional[str] = None
    text: Optional[str] = None
    prompt_used: Optional[str] = None


# ============================================================
#  1) 生成虛擬試衣圖片
# ============================================================
@router.post("/generate", response_model=VirtualFittingResponse)
async def generate_virtual_fitting(
    request: VirtualFittingRequest,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db),
):
    """
    Generate realistic AI-powered virtual try-on image

    使用 Gemini / Vertex AI Image 服務，
    根據使用者選擇的衣物 + 照片（如果有）產生實際試穿圖。
    """
    logger.info(f"收到虛擬試衣請求：{len(request.selected_items)} 件衣物")

    try:
        if not request.selected_items:
            logger.warning("請求中沒有選擇任何衣物")
            raise HTTPException(status_code=400, detail="No clothing items selected")
        
        # ✨ 獲取用戶身體數據（身形類型和 BMI）
        body_data = None
        body_shape_type = None
        bmi_value = None
        bmi_category = None
        
        try:
            # 從 body_metrics 表查詢用戶身體數據
            body_metrics_query = text("""
                SELECT height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, sex
                FROM body_metrics
                WHERE user_id = :user_id
                LIMIT 1
            """)
            result = db.execute(body_metrics_query, {"user_id": current_user.id})
            body_metrics = result.mappings().first()
            
            if body_metrics:
                body_data = dict(body_metrics)
                height_cm = body_data.get('height_cm')
                weight_kg = body_data.get('weight_kg')
                chest_cm = body_data.get('chest_cm')
                waist_cm = body_data.get('waist_cm')
                hip_cm = body_data.get('hip_cm')
                shoulder_cm = body_data.get('shoulder_cm')
                sex = body_data.get('sex', '女')
                
                # 計算 BMI
                if height_cm and weight_kg and height_cm > 0:
                    height_m = height_cm / 100
                    bmi_value = round(weight_kg / (height_m * height_m), 1)
                    
                    # BMI 分類
                    if bmi_value < 18.5:
                        bmi_category = '體重過輕'
                    elif bmi_value < 24:
                        bmi_category = '正常範圍'
                    elif bmi_value < 27:
                        bmi_category = '過重'
                    elif bmi_value < 30:
                        bmi_category = '輕度肥胖'
                    else:
                        bmi_category = '中度肥胖'
                    
                    logger.info(f"用戶 BMI: {bmi_value} ({bmi_category})")
                
                # 判斷身形類型（女性）
                if sex == '女' and all([chest_cm, waist_cm, hip_cm, shoulder_cm]):
                    diff_bw = chest_cm - waist_cm  # 胸圍 - 腰圍
                    diff_hw = hip_cm - waist_cm    # 臀圍 - 腰圍
                    diff_bh = abs(chest_cm - hip_cm)  # 胸臀差
                    shoulder_x2 = shoulder_cm * 2
                    diff_hs = hip_cm - shoulder_x2  # 臀圍 - 肩寬×2
                    diff_sh = shoulder_x2 - hip_cm  # 肩寬×2 - 臀圍
                    
                    # 按照前端相同的判斷順序
                    if (diff_bw >= 12 and diff_bw <= 28) and (diff_hw >= 15 and diff_hw <= 33) and (diff_bh <= 7):
                        body_shape_type = '沙漏型身材'
                    elif diff_sh > 5:
                        body_shape_type = '倒三角身材'
                    elif diff_hs > 5 and hip_cm > chest_cm + 3:
                        body_shape_type = '梨型身材'
                    elif diff_bw < 15 or diff_hw < 20:
                        body_shape_type = 'H型身材'
                    elif waist_cm > hip_cm:
                        body_shape_type = '蘋果型身材'
                    else:
                        body_shape_type = '標準身材'
                    
                    logger.info(f"用戶身形類型: {body_shape_type}")
                
                # 判斷身形類型（男性）
                elif sex == '男' and all([waist_cm, hip_cm, shoulder_cm]):
                    shoulder_x2 = shoulder_cm * 2
                    diff_hs = hip_cm - shoulder_x2
                    diff_sh = shoulder_x2 - hip_cm
                    
                    if waist_cm > hip_cm:
                        body_shape_type = '蘋果型身材'
                    elif diff_hs > 3:
                        body_shape_type = '梨型身材'
                    elif diff_sh > 3:
                        body_shape_type = '倒三角身材'
                    elif abs(diff_sh) < 3:
                        body_shape_type = 'H型身材'
                    else:
                        body_shape_type = '標準身材'
                    
                    logger.info(f"用戶身形類型: {body_shape_type}")
        
        except Exception as e:
            logger.warning(f"獲取身體數據失敗: {e}，將不使用身體數據生成")

        # ✅ 從資料庫重新獲取衣物資料，確保圖片 URL 是最新的 GCS URI
        items_dict = []

        for item in request.selected_items:
            # 解析 item_id（支援字串和整數）
            try:
                item_id = int(item.id)
            except Exception:
                item_id = item.id

            db_item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()

            if db_item:
                items_dict.append(
                    {
                        "id": str(db_item.id),
                        "name": db_item.name or item.name,
                        "category": db_item.category.value if db_item.category else item.category,
                        "img": db_item.cover_image_url,  # ✅ 直接使用 GCS URI (gs://...)
                    }
                )
                logger.info(
                    f"從資料庫載入衣物 ID={db_item.id}, 圖片 URL={db_item.cover_image_url}"
                )
            else:
                logger.warning(f"資料庫中找不到衣物 ID={item.id}，使用前端資料")
                items_dict.append(item.dict())

        # 建立 prompt（整合身體數據）
        prompt = image_service.create_fashion_prompt(
            clothing_items=items_dict,
            user_input=request.user_input,
            style="casual",
            body_shape_type=body_shape_type,
            bmi_value=bmi_value,
            bmi_category=bmi_category,
        )

        # 處理用戶照片（優先級：上傳圖片 > 用戶頭貼 > 預設模特兒）
        user_photo_base64 = None
        photo_source = "預設模特兒"

        if request.user_photo:
            # 最高優先級：前端上傳的照片
            if request.user_photo.startswith("data:image"):
                user_photo_base64 = (
                    request.user_photo.split(",", 1)[1]
                    if "," in request.user_photo
                    else request.user_photo
                )
            else:
                user_photo_base64 = request.user_photo
            photo_source = "上傳照片"
            logger.info("✅ 檢測到上傳照片（最高優先級），將使用個性化生成")
        elif current_user.picture:
            # 次高優先級：使用用戶頭貼（GCS URI 或 HTTP URL）
            try:
                if current_user.picture.startswith("gs://"):
                    logger.info("嘗試從 GCS 載入用戶頭貼")
                    user_photo_base64 = await image_service.download_user_photo_from_gcs(
                        current_user.picture,
                        str(current_user.id)
                    )
                    photo_source = "用戶頭貼 (GCS)"
                else:
                    logger.info("嘗試從 HTTP URL 載入用戶頭貼")
                    user_photo_base64 = image_service.download_user_photo_from_url(
                        current_user.picture
                    )
                    photo_source = "用戶頭貼 (URL)"
                logger.info("✅ 成功載入用戶頭貼，用於個性化生成")
            except Exception as e:
                logger.warning(
                    f"⚠️ 載入用戶頭貼時發生錯誤: {str(e)}，將使用預設模特兒"
                )
        else:
            logger.info("ℹ️ 未提供照片且無用戶頭貼，將使用預設模特兒")

        # 呼叫 AI 生成圖片
        logger.info(f"開始生成圖片，使用提示詞長度：{len(prompt)} 字元")
        logger.info(f"傳遞 {len(items_dict)} 件衣物數據到圖片生成服務")

        result = await image_service.generate_tryon_image(
            prompt=prompt,
            style="realistic",
            width=768,
            height=1024,
            clothing_items=items_dict,
            user_photo_base64=user_photo_base64,
        )
        logger.info(f"圖片生成結果：success={result.get('success')}")

        if result.get("success"):
            image_base64 = result.get("image_base64")
            data_url = f"data:image/png;base64,{image_base64}"

            clothing_images_used = result.get("clothing_images_used", 0)

            logger.info("圖片生成成功，返回 base64 數據")
            logger.info(f"使用衣物圖片數量: {clothing_images_used}")
            logger.info(f"照片來源: {photo_source}")

            # 組合生成資訊
            generation_info_parts = [
                f"✅ 使用 {clothing_images_used} 張實際衣物圖片生成 (Image-to-Image)",
                f"📸 照片來源: {photo_source}"
            ]
            
            if body_shape_type:
                generation_info_parts.append(f"👤 身形類型: {body_shape_type}")
            if bmi_value and bmi_category:
                generation_info_parts.append(f"📊 BMI: {bmi_value} ({bmi_category})")
            
            generation_info = "\n".join(generation_info_parts)

            return VirtualFittingResponse(
                type="image",
                url=data_url,
                prompt_used=result.get("prompt"),
                text=generation_info,
            )
        else:
            error_msg = result.get("error", "虛擬試衣生成失敗")
            logger.warning(f"圖片生成失敗：{error_msg}")

            if "未提供衣物圖片" in error_msg:
                help_text = f"""❌ {error_msg}

**虛擬試衣需求：**
- 必須選擇至少一件有圖片的衣物
- 系統會使用實際衣物圖片進行 Image-to-Image 生成
- 不支援純文字描述生成"""
            elif "未配置 GEMINI_API_KEY" in error_msg:
                help_text = f"""❌ {error_msg}

**如何啟用虛擬試衣功能：**
1. 前往 GCP Console 啟用 Vertex AI / Generative AI 服務
2. 建立或取得 Gemini API Key
3. 在後端 .env 中設定 GEMINI_API_KEY
4. 重新啟動後端服務"""
            else:
                help_text = f"""❌ 虛擬試衣生成失敗：{error_msg}

請稍後再試，或聯絡系統管理員。"""

            return VirtualFittingResponse(
                type="text",
                text=help_text,
                prompt_used=result.get("prompt"),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"虛擬試衣生成失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"虛擬試衣生成失敗: {e}")

# ============================================================
#  2) 保存虛擬試衣結果到 GCS + DB
# ============================================================
class SaveOutfitRequest(BaseModel):
    """
    保存穿搭的請求資料。

    - worn_date: YYYY-MM-DD
    - file_name: 可選的檔名（不含副檔名），若未提供會自動產生
    - image_data / image_url: 前端傳來的圖片（可為 base64 或 data URL）
    - item_ids: 參與生成的衣物 ID 列表（可選）
    - title / description / tags: 穿搭文字資訊（可選）
    - sync_to_post: 是否同步發佈貼文（目前僅預留，後端可視需要實作）
    """

    worn_date: str
    file_name: Optional[str] = None
    image_data: Optional[str] = None
    image_url: Optional[str] = None
    item_ids: Optional[List[int]] = []
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    sync_to_post: bool = False

class SaveOutfitResponse(BaseModel):
    success: bool
    outfit_id: int
    image_url: str  # GCS URI
    signed_url: Optional[str] = None

OUTFIT_BUCKET_NAME = (
    os.getenv("GCS_BUCKET_OUTFIT")
    or os.getenv("OUTFIT_GCS_BUCKET")
    or "smartclothes_outfit"
)

@router.post("/save-outfit", response_model=SaveOutfitResponse)
async def save_outfit_from_virtual_fitting(
    payload: SaveOutfitRequest,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db),
):
    """
    將前端的虛擬試衣結果保存到 GCS 與資料庫。

    - 接受前端傳來的 data URL / base64 圖片（image_data 或 image_url）
    - 會自動上傳到 GCS 指定 bucket，並建立一筆 Outfit
    - 同時可以綁定 item_ids，並寫入標題 / 描述 / 標籤
    """
    try:
        # 1) 解析日期與時間（支援多種格式），若只提供日期則時間為 00:00；轉為 timezone-aware (UTC)
        def _parse_worn_date(s: str) -> datetime:
            if not s or not isinstance(s, str):
                raise HTTPException(status_code=400, detail="worn_date 必須為字串，格式如 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM' 或 ISO')")
            v = s.strip()
            # 優先嘗試 ISO 格式
            try:
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

            fmts = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
            for f in fmts:
                try:
                    dt = datetime.strptime(v, f)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except Exception:
                    continue

            raise HTTPException(status_code=400, detail="worn_date 解析失敗，請使用 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM' 或 ISO 格式")

        parsed_dt = _parse_worn_date(payload.worn_date)
        # 使用前端提供的日期，時間部分使用當前伺服器時間（UTC）
        now_utc = datetime.now(timezone.utc)
        worn_date_obj = datetime(
            parsed_dt.year,
            parsed_dt.month,
            parsed_dt.day,
            now_utc.hour,
            now_utc.minute,
            now_utc.second,
            tzinfo=timezone.utc,
        )
        logger.info(f"Parsed save-outfit worn_date: input='{payload.worn_date}' -> parsed_date={parsed_dt.date()!r}, time_from_now={now_utc.time()!r}, combined={worn_date_obj!r}")

        # 2) 取得圖片來源（支援 image_data 或 image_url，優先使用 image_data）
        img_b64 = payload.image_data or payload.image_url
        if not img_b64:
            raise HTTPException(status_code=400, detail="必須提供 image_data 或 image_url")

        if img_b64.startswith("data:image"):
            img_b64 = img_b64.split(",", 1)[1] if "," in img_b64 else img_b64

        # 3) base64 解碼
        try:
            raw_bytes = base64.b64decode(img_b64)
        except Exception:
            raise HTTPException(status_code=400, detail="image_data / image_url 非有效 base64")

        # 4) 轉為 JPEG bytes
        try:
            im = Image.open(BytesIO(raw_bytes))
            rgb_im = im.convert("RGB")
            img_buffer = BytesIO()
            rgb_im.save(img_buffer, format="JPEG", quality=92)
            jpeg_bytes = img_buffer.getvalue()
        except Exception:
            raise HTTPException(status_code=400, detail="無法解析圖片資料")

        # 5) 準備檔名與 GCS 路徑
        base_name = (payload.title or payload.file_name or payload.worn_date or "outfit").strip()
        if not base_name:
            base_name = "outfit"

        safe_name = (
            base_name.replace("/", "_")
            .replace("\\", "_")
            .replace("?", "_")
            .replace(":", "_")
            .replace("*", "_")
            .replace("|", "_")
            .replace("\"", "_")
            .replace("<", "_")
            .replace(">", "_")
        )

        user_id_str = str(current_user.id)

        # ✅ 你指定的路徑：smartclothesoutfit/user_id/前端title名稱.jpg
        gcs_blob_path = f"{user_id_str}/{safe_name}.jpg"

        # 6) 上傳到 GCS 指定 bucket
        gcs_uri = upload_file_to_gcs_from_bytes(
            file_bytes=jpeg_bytes,
            destination_blob_name=gcs_blob_path,
            mime_type="image/jpeg",
            bucket_name=OUTFIT_BUCKET_NAME,
            public=False,
        )

        # 7) 寫入資料庫（Outfit）
        outfit = Outfit(
            user_id=current_user.id,
            worn_date=worn_date_obj,
            image_url=gcs_uri,
        )

        if payload.title is not None:
            outfit.name = payload.title.strip()
        if payload.description is not None:
            outfit.description = payload.description.strip()
        if payload.tags is not None:
            outfit.tags = payload.tags.strip()

        if payload.item_ids:
            items = (
                db.query(WardrobeItem)
                .filter(WardrobeItem.id.in_(payload.item_ids))
                .all()
            )
            outfit.items = items

        db.add(outfit)

        if payload.sync_to_post:
            now = datetime.now(timezone.utc)
            media_obj = [
                {
                    "type": "image",
                    "gcs_uri": gcs_uri,
                    "is_cover": True,
                }
            ]

            sql = text(
                """
                INSERT INTO user_post
                    (user_id, type, title, tag, content, media, visibility,
                     like_count, comment_count, created_at, updated_at)
                VALUES
                    (:user_id, :type, :title, :tag, :content, :media, :visibility,
                     :like_count, :comment_count, :created_at, :updated_at)
                """
            )
            params = {
                "user_id": getattr(current_user, "id", None),
                "type": "post",
                "title": (payload.title or "").strip(),
                "tag": (payload.tags or "").strip(),
                "content": (payload.description or "").strip(),
                "media": json.dumps(media_obj),
                "visibility": "public",
                "like_count": 0,
                "comment_count": 0,
                "created_at": now,
                "updated_at": now,
            }

            db.execute(sql, params)

        db.commit()
        db.refresh(outfit)

        signed_url = None
        try:
            signed_url = generate_signed_url_from_gcs_uri(gcs_uri)
        except Exception as e:
            logger.warning(f"生成簽名 URL 失敗: {e}")

        return SaveOutfitResponse(
            success=True,
            outfit_id=outfit.id,
            image_url=gcs_uri,
            signed_url=signed_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"保存穿搭失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存穿搭失敗: {e}")


# ============================================================
#  3) 上傳實體照片版的虛擬試衣（保留原本功能）
# ============================================================
@router.post("/generate-with-photo")
async def generate_with_user_photo(
    user_photo: UploadFile = File(...),
    clothing_items: str = Form(...),
    user_input: str = Form(default="時尚日常穿搭"),
):
    """
    Generate virtual try-on using user's uploaded photo
    This provides more personalized results by analyzing the user's appearance
    """
    try:
        image_data = await user_photo.read()
        image = Image.open(BytesIO(image_data))

        if image.mode != "RGB":
            image = image.convert("RGB")

        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format="JPEG")
        img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

        try:
            items = json.loads(clothing_items)
        except Exception:
            items = []

        clothing_prompt = image_service.create_fashion_prompt(
            clothing_items=items,
            user_input=user_input,
            style="casual",
        )

        try:
            enhancement_result = await image_service.enhance_with_user_photo(
                user_photo_base64=img_base64,
                base_prompt=clothing_prompt,
            )
        except Exception as e:
            logger.error(f"User photo enhancement failed: {e}", exc_info=True)
            enhancement_result = {"success": False, "error": str(e)}

        if enhancement_result.get("success"):
            enhanced_prompt = enhancement_result.get("enhanced_prompt", clothing_prompt)

            result = await image_service.generate_tryon_image(
                prompt=enhanced_prompt,
                style="realistic",
                width=768,
                height=1024,
                clothing_items=items,
                user_photo_base64=img_base64,
            )

            if result.get("success"):
                image_base64 = result.get("image_base64")
                data_url = f"data:image/png;base64,{image_base64}"

                return {
                    "type": "image",
                    "url": data_url,
                    "analysis": enhancement_result.get("analysis"),
                    "prompt_used": enhanced_prompt,
                }
            else:
                return {
                    "type": "text",
                    "text": f"圖片生成失敗：{result.get('error')}",
                    "analysis": enhancement_result.get("analysis"),
                }
        else:
            return {
                "type": "text",
                "text": f"照片分析失敗：{enhancement_result.get('error')}",
                "message": "請確保已設定 GEMINI_API_KEY",
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Photo processing failed: {str(e)}")
