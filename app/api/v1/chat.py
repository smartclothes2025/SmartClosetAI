# app/api/v1/chat.py
from fastapi import APIRouter, HTTPException, Body
# 確保您的 app.services.fashion_advisor 導入路徑正確
from app.services.fashion_advisor import FashionAdvisor
from typing import Dict, Any, Union
import logging 

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

router = APIRouter()

# 嘗試初始化 Advisor，如果失敗會記錄錯誤
try:
    # 假設 FashionAdvisor 不需要參數，或者使用 .env 讀取
    advisor = FashionAdvisor()
    logger.info("FashionAdvisor 初始化成功。")
except Exception as e:
    logger.error(f"初始化 FashionAdvisor 失敗: {e}", exc_info=True)
    advisor = None

@router.get("/ping")
def ping():
    logger.info("收到 /ping 請求")
    return {"message": "pong"}

@router.post("/")
def get_outfit_recommendation(payload: Dict[str, str] = Body(...)) -> Dict[str, Any]:
    """
    根據使用者輸入自由文字，自動推薦穿搭，並直接返回影像 URL 或文字。
    """
    logger.info(f"收到 / 請求，payload: {payload}")
    
    if advisor is None:
        logger.error("FashionAdvisor 未成功初始化，無法處理請求。")
        raise HTTPException(status_code=500, detail="服務器內部錯誤：Advisor 未初始化")
        
    user_input = payload.get("user_input")
    user_image_data = payload.get("user_image_data") # 假設前端可能會傳來圖片

    if not user_input:
        logger.error("缺少 user_input")
        raise HTTPException(status_code=400, detail="缺少 user_input")
        
    try:
        # 呼叫您修正後的函式
        result = advisor.process_user_input(user_input, user_image_data)
        logger.info(f"FashionAdvisor 返回結果: {result}")
        
        # --- 這是修正後的檢查邏輯 ---

        # 檢查基本格式是否為字典，以及是否有 'type' 鍵
        if not isinstance(result, dict) or "type" not in result:
            logger.error(f"FashionAdvisor 返回了未知格式的結果: {result}")
            raise HTTPException(status_code=500, detail="服務器內部錯誤: FashionAdvisor 返回格式異常")

        # 情況一：成功生成圖片
        # FashionAdvisor 回傳: {"type": "image", "url": "...", "text": "..."}
        if result["type"] == "image":
            if "url" in result and "text" in result:
                logger.info(f"FashionAdvisor 判斷為影像回應，URL: {result['url']}")
                # 這個格式已經很完美，直接回傳給前端
                return result
            else:
                logger.error(f"FashionAdvisor 回應類型為 image，但缺少 'url' 或 'text': {result}")
                raise HTTPException(status_code=500, detail="服務器內部錯誤: 影像回應格式不完整")
                
        # 情況二：純文字回應 (包含一般聊天或錯誤訊息)
        # FashionAdvisor 回傳: {"type": "text", "text": "..."}
        elif result["type"] == "text":
            if "text" in result:
                logger.info("FashionAdvisor 判斷為文字回應。")
                # 這個格式也很好，直接回傳
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