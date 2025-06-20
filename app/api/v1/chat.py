# api/v1/chat.py

from fastapi import APIRouter, HTTPException, Body
from app.services.fashion_advisor import FashionAdvisor
from typing import Dict
import asyncio

router = APIRouter()

advisor = FashionAdvisor()

@router.post("/")
async def get_outfit_recommendation(payload: Dict[str, str] = Body(...)):
    """
    根據使用者輸入自由文字，自動推薦穿搭。
    """
    user_input = payload.get("user_input")
    if not user_input:
        raise HTTPException(status_code=400, detail="缺少 user_input")

    try:
        result = await advisor.get_outfit_advice_from_free_text(user_input)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系統錯誤：{str(e)}")
    