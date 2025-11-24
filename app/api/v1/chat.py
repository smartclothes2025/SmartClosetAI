# app/api/v1/chat.py - 修正版
from fastapi import APIRouter, HTTPException, Body, Depends, Request
from app.services.fashion_advisor import FashionAdvisor
from typing import Dict, Any, Union, Optional
import logging
from app.models.auth import User
from app.core.db import get_db
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
import uuid as _uuid
LOG_FILE_PATH = 'smartcloset_activity.log'
# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=LOG_FILE_PATH,# 將日誌寫入檔案
    filemode='a'
)
logger = logging.getLogger(__name__)

router = APIRouter()

# 嘗試初始化 Advisor，如果失敗會記錄錯誤
try:
    advisor = FashionAdvisor()
    logger.info("FashionAdvisor 初始化成功。")
except Exception as e:
    logger.error(f"初始化 FashionAdvisor 失敗: {e}", exc_info=True)
    advisor = None

import sys

@router.get("/ping")
def ping():
    logger.info("收到 /ping 請求")
    print("--- 應用程式內部 print：收到 /ping 請求 ---")
    sys.stderr.write("--- 最終測試：sys.stderr.write 輸出 ---\n")
    sys.stderr.flush()
    return {"message": "pong"}

class ChatRequest(BaseModel):
    user_input: str
    user_image_data: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    city: Optional[str] = None

@router.post("/")
async def get_outfit_recommendation(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    根據使用者輸入自由文字，自動推薦穿搭，並直接返回影像 URL 或文字。
    """
    # 自行處理認證邏輯
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token 無效")

    token = auth_header.split(" ", 1)[1]
    prefix = "user-"
    suffix = "-token"

    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        raise HTTPException(status_code=401, detail="Token 無效")

    user_id_str = token[len(prefix):-len(suffix)] if len(token) > (len(prefix) + len(suffix)) else ""

    # 驗證 UUID 格式
    try:
        _uuid.UUID(user_id_str)
    except Exception:
        raise HTTPException(status_code=401, detail="Token 無效")

    # 查詢使用者
    current_user = db.query(User).filter(User.id == user_id_str).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="使用者不存在")

    user_id = str(current_user.id)
    logger.info(f"收到 / 請求，User ID: {user_id}, Payload: {payload}")

    if advisor is None:
        logger.error("FashionAdvisor 未成功初始化，無法處理請求。")
        raise HTTPException(status_code=500, detail="服務器內部錯誤：Advisor 未初始化")

    user_input = payload.user_input
    user_image_data = payload.user_image_data

    if not user_input:
        logger.error("缺少 user_input")
        raise HTTPException(status_code=400, detail="缺少 user_input")

    try:
        # 🔥 關鍵修正區塊：淨化 Base64 數據
        cleaned_image_data = None
        if user_image_data:
            # 參考 virtual_fitting.py 的處理方式，移除 Data URI Scheme
            if user_image_data.startswith("data:image"):
                cleaned_image_data = (
                    user_image_data.split(",", 1)[1]
                    if "," in user_image_data
                    else user_image_data
                )
                logger.info("✅ Chat API: 已移除 Data URI Scheme，淨化 Base64 數據")
            else:
                cleaned_image_data = user_image_data

        # 獲取用戶頭貼 URI
        picture_uri = current_user.picture if hasattr(current_user, 'picture') else None
        logger.info(f"📸 用戶頭貼 URI: {picture_uri}")

        # 🔥 獲取用戶性別
        user_gender = None
        if hasattr(current_user, "gender") and getattr(current_user, "gender", None):
            raw_gender = getattr(current_user, "gender")
            # 正規化性別
            v = str(raw_gender).strip().lower()
            if any(token in v for token in ["女", "female", "woman", "women", "girl"]):
                user_gender = "women"
            elif any(token in v for token in ["男", "male", "man", "men", "boy"]):
                user_gender = "men"
            else:
                user_gender = "women"  # 預設女性
        else:
            # 從 body_metrics 表獲取性別
            try:
                from sqlalchemy import text
                row = db.execute(
                    text(
                        "SELECT sex FROM body_metrics "
                        "WHERE user_id = :uid "
                        "ORDER BY recorded_at DESC "
                        "LIMIT 1"
                    ),
                    {"uid": str(current_user.id)},
                ).mappings().first()
                if row:
                    raw_sex = row.get("sex")
                    v = str(raw_sex).strip().lower()
                    if any(token in v for token in ["女", "female", "woman", "women", "girl"]):
                        user_gender = "women"
                    elif any(token in v for token in ["男", "male", "man", "men", "boy"]):
                        user_gender = "men"
                    else:
                        user_gender = "women"
            except Exception as e:
                logger.warning(f"無法從 body_metrics 獲取性別: {e}")
                user_gender = "women"  # 預設女性

        logger.info(f"👤 用戶性別: {user_gender}")

        result = await advisor.process_user_input(
            user_id=user_id,
            user_input=user_input,
            user_image_data=cleaned_image_data, # ⬅️ 傳遞淨化後的數據
            picture_uri=picture_uri,
            user_gender=user_gender  # 🔥 傳遞用戶性別
        )

        logger.info(f"Advisor 返回結果: {result}")

        # --- 返回結果檢查邏輯 (保持不變) ---

        if not isinstance(result, dict) or "type" not in result:
            logger.error(f"FashionAdvisor 返回了未知格式的結果: {result}")
            raise HTTPException(status_code=500, detail="服務器內部錯誤: FashionAdvisor 返回格式異常")

        # 情況一：成功生成圖片
        if result["type"] == "image":
            if "url" in result and "text" in result:
                logger.info(f"FashionAdvisor 判斷為影像回應，URL: {result['url']}")
                return result
            else:
                logger.error(f"FashionAdvisor 回應類型為 image，但缺少 'url' 或 'text': {result}")
                raise HTTPException(status_code=500, detail="服務器內部錯誤: 影像回應格式不完整")

        # 情況二：純文字回應
        elif result["type"] == "text":
            if "text" in result:
                logger.info("FashionAdvisor 判斷為文字回應。")
                return result
            else:
                logger.error(f"FashionAdvisor 回應類型為 text，但缺少 'text': {result}")
                raise HTTPException(status_code=500, detail="服務器內部錯誤: 文字回應格式不完整")

        # 情況三：未知的 'type'
        else:
            logger.error(f"FashionAdvisor 返回了未知的 'type': {result}")
            raise HTTPException(status_code=500, detail="服務器內部錯誤: FashionAdvisor 返回類型不明確")

    except HTTPException as http_e:
        # 重新拋出已知的 HTTP 錯誤
        logger.warning(f"處理請求時發生 HTTP 錯誤: {http_e.detail}")
        raise http_e
    except Exception as e:
        # 捕獲所有其他未知錯誤
        logger.error(f"處理請求時發生系統錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"系統錯誤：{str(e)}")