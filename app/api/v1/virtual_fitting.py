#app/api/v1/virtual_fitting.py
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

# Import our image generation service
from app.services.image_generation import image_service
from app.core.db import get_db
from app.models.auth import User

# Setup logger
logger = logging.getLogger(__name__)

# 用於 JSON body 端點的用戶認證（只從 Header 讀取）
def get_current_user_from_header(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    從 Header 的 Authorization: Bearer user-<uuid>-token 驗證使用者
    專用於 JSON body 端點，避免與 Form 參數衝突
    """
    from app.api.v1.auth import AUTH_BEARER_PREFIX, ERR_INVALID_TOKEN, ERR_USER_NOT_FOUND
    import uuid as _uuid
    
    # 讀取 Header Bearer
    auth_header = request.headers.get("Authorization", "")
    token = None
    
    if auth_header.startswith(AUTH_BEARER_PREFIX):
        token = auth_header.split(" ", 1)[1]
    
    # 無 token
    if not token:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    # 解析 UUID
    user_id = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""
    try:
        _uuid.UUID(user_id)  # 驗證格式
    except Exception:
        raise HTTPException(status_code=401, detail=ERR_INVALID_TOKEN)
    
    # 查 DB
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=ERR_USER_NOT_FOUND)
    return user

router = APIRouter(tags=["virtual-fitting"])


class ClothingItem(BaseModel):
    id: str  # 支援 UUID 字串
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




@router.post("/generate", response_model=VirtualFittingResponse)
async def generate_virtual_fitting(
    request: VirtualFittingRequest,
    current_user: User = Depends(get_current_user_from_header),
    db: Session = Depends(get_db)
):
    """
    Generate realistic AI-powered virtual try-on image
    
    This endpoint uses AI image generation services (Google Gemini/Imagen)
    to create realistic try-on visualizations based on selected clothing items.
    """
    logger.info(f"收到虛擬試衣請求：{len(request.selected_items)} 件衣物")
    
    try:
        if not request.selected_items:
            logger.warning("請求中沒有選擇任何衣物")
            raise HTTPException(status_code=400, detail="No clothing items selected")
        
        # ✅ 從資料庫重新獲取衣物資料，確保圖片 URL 是最新的 GCS URI
        from app.models.wardrobe import WardrobeItem
        items_dict = []
        
        for item in request.selected_items:
            # 解析 item_id（支援字串和整數）
            try:
                item_id = int(item.id)
            except:
                item_id = item.id
            
            # 從資料庫查詢衣物
            db_item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()
            
            if db_item:
                # 使用資料庫中的原始 GCS URI（不是簽署 URL）
                items_dict.append({
                    'id': str(db_item.id),
                    'name': db_item.name or item.name,
                    'category': db_item.category.value if db_item.category else item.category,
                    'img': db_item.cover_image_url  # ✅ 直接使用 GCS URI (gs://...)
                })
                logger.info(f"從資料庫載入衣物 ID={db_item.id}, 圖片 URL={db_item.cover_image_url}")
            else:
                # 如果資料庫中找不到，使用前端傳來的資料（但可能沒有圖片）
                logger.warning(f"資料庫中找不到衣物 ID={item.id}，使用前端資料")
                items_dict.append(item.dict())
        
        # Create optimized fashion prompt (不使用身體數據)
        prompt = image_service.create_fashion_prompt(
            clothing_items=items_dict,
            user_input=request.user_input,
            style="casual"
        )
        
        # 處理用戶照片（優先級：上傳圖片 > 用戶頭貼 > 預設模特兒）
        user_photo_base64 = None
        photo_source = "預設模特兒"
        
        if request.user_photo:
            # 最高優先級：前端上傳的照片
            if request.user_photo.startswith('data:image'):
                # 格式: data:image/jpeg;base64,/9j/4AAQ...
                user_photo_base64 = request.user_photo.split(',', 1)[1] if ',' in request.user_photo else request.user_photo
            else:
                user_photo_base64 = request.user_photo
            photo_source = "上傳照片"
            logger.info("✅ 檢測到上傳照片（最高優先級），將使用個性化生成")
        elif current_user.picture:
            # 次優先級：用戶頭貼（從 GCS 下載）
            try:
                logger.info(f"📸 嘗試從用戶頭貼載入照片: {current_user.picture}")
                user_photo_base64 = await image_service.download_user_photo_from_gcs(
                    current_user.picture,
                    current_user.id
                )
                if user_photo_base64:
                    photo_source = "用戶頭貼"
                    logger.info("✅ 成功載入用戶頭貼，將使用個性化生成")
                else:
                    logger.warning("⚠️ 用戶頭貼載入失敗，將使用預設模特兒")
            except Exception as e:
                logger.warning(f"⚠️ 載入用戶頭貼時發生錯誤: {str(e)}，將使用預設模特兒")
        else:
            logger.info("ℹ️ 未提供照片且無用戶頭貼，將使用預設模特兒")
        
        # Generate image using available AI service with clothing items
        logger.info(f"開始生成圖片，使用提示詞長度：{len(prompt)} 字元")
        logger.info(f"傳遞 {len(items_dict)} 件衣物數據到圖片生成服務")
        
        result = await image_service.generate_tryon_image(
            prompt=prompt,
            style="realistic",
            width=768,
            height=1024,
            clothing_items=items_dict,  # 傳遞衣物數據（包含 GCS URI）
            user_photo_base64=user_photo_base64  # 傳遞用戶照片（如果有）
        )
        logger.info(f"圖片生成結果：success={result.get('success')}")
        
        if result.get("success"):
            # Convert base64 to data URL for frontend
            image_base64 = result.get("image_base64")
            data_url = f"data:image/png;base64,{image_base64}"
            
            # 獲取生成資訊
            clothing_images_used = result.get("clothing_images_used", 0)
            
            logger.info(f"圖片生成成功，返回 base64 數據")
            logger.info(f"使用衣物圖片數量: {clothing_images_used}")
            logger.info(f"照片來源: {photo_source}")
            
            # 構建提示訊息
            generation_info = f"✅ 使用 {clothing_images_used} 張實際衣物圖片生成 (Image-to-Image)\n📸 照片來源: {photo_source}"
            
            return VirtualFittingResponse(
                type="image",
                url=data_url,
                prompt_used=result.get("prompt"),
                text=generation_info
            )
        else:
            # 生成失敗，返回錯誤訊息
            error_msg = result.get("error", "虛擬試衣生成失敗")
            logger.warning(f"圖片生成失敗：{error_msg}")
            
            # 根據錯誤類型提供不同的提示
            if "未提供衣物圖片" in error_msg:
                help_text = f"""❌ {error_msg}

**虛擬試衣需求：**
- 必須選擇至少一件有圖片的衣物
- 系統會使用實際衣物圖片進行 Image-to-Image 生成
- 不支援純文字描述生成"""
            elif "未配置 GEMINI_API_KEY" in error_msg:
                help_text = f"""❌ {error_msg}

**如何啟用虛擬試衣功能：**
1. 註冊 Google Gemini API：https://makersuite.google.com/app/apikey
2. 獲取 API Key
3. 在 .env 文件中設定：GEMINI_API_KEY=your_key
4. 重啟後端服務

**當前配置狀態：**
- GEMINI_API_KEY: {'✅ 已配置' if os.getenv('GEMINI_API_KEY') else '❌ 未配置'}"""
            else:
                help_text = f"""❌ 虛擬試衣生成失敗

錯誤訊息：{error_msg}

**故障排除：**
1. 確認所選衣物都有圖片
2. 檢查網路連線
3. 確認 GEMINI_API_KEY 配置正確
4. 查看後端日誌獲取詳細錯誤資訊"""
            
            return VirtualFittingResponse(
                type="text",
                text=help_text,
                prompt_used=prompt
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"虛擬試衣生成異常：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失敗: {str(e)}")




@router.post("/generate-with-photo")
async def generate_with_user_photo(
    user_photo: UploadFile = File(...),
    clothing_items: str = Form(...),
    user_input: str = Form(default="時尚日常穿搭")
):
    """
    Generate virtual try-on using user's uploaded photo
    This provides more personalized results by analyzing the user's appearance
    """
    try:
        # Read and process user photo
        image_data = await user_photo.read()
        image = Image.open(BytesIO(image_data))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert image to base64
        img_byte_arr = BytesIO()
        image.save(img_byte_arr, format='JPEG')
        img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
        
        # Parse clothing items
        try:
            items = json.loads(clothing_items)
        except:
            items = []
        
        # Create clothing prompt
        clothing_prompt = image_service.create_fashion_prompt(
            clothing_items=items,
            user_input=user_input,
            style="casual"
        )
        
        # Enhance prompt with user photo analysis
        enhancement_result = await image_service.enhance_with_user_photo(
            user_photo_base64=img_base64,
            clothing_prompt=clothing_prompt
        )
        
        if enhancement_result.get("success"):
            # Use enhanced prompt to generate image
            enhanced_prompt = enhancement_result.get("enhanced_prompt")
            
            result = await image_service.generate_tryon_image(
                prompt=enhanced_prompt,
                style="realistic",
                width=768,
                height=1024
            )
            
            if result.get("success"):
                image_base64 = result.get("image_base64")
                data_url = f"data:image/png;base64,{image_base64}"
                
                return {
                    "type": "image",
                    "url": data_url,
                    "analysis": enhancement_result.get("analysis"),
                    "prompt_used": enhanced_prompt
                }
            else:
                return {
                    "type": "text",
                    "text": f"圖片生成失敗：{result.get('error')}",
                    "analysis": enhancement_result.get("analysis")
                }
        else:
            return {
                "type": "text",
                "text": f"照片分析失敗：{enhancement_result.get('error')}",
                "message": "請確保已設定 GEMINI_API_KEY"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Photo processing failed: {str(e)}")
