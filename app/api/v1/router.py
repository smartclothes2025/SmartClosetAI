#api/v1/router.py
from fastapi import APIRouter
from .auth import router as auth_router
from .weather import router as weather_router
from .upload import router as upload_router
from .chat import router as chat_router
from .price_suggestion import router as price_suggestion_router
from .clothes import router as clothes_router
from .users import router as users_router
from .posts import router as posts_router
from .outfits import router as outfits_router

api_router = APIRouter()

# —— 新增這支跳過 DB 的假 endpoint ——
@api_router.get("/ping-db")
async def ping_db():
    return {"db_ping": "2025-08-02T12:00:00"}

api_router.include_router(auth_router, prefix="/auth", tags=["認證"])  
api_router.include_router(weather_router, prefix="/weather", tags=["天氣與穿搭"])
api_router.include_router(upload_router, prefix="/upload", tags=["上傳"])
api_router.include_router(chat_router, prefix="/chat", tags=["聊天"])
api_router.include_router(price_suggestion_router, prefix="/price-suggestion", tags=["估價"])
api_router.include_router(clothes_router, tags=["衣服"])
api_router.include_router(users_router, tags=["帳號"])
api_router.include_router(posts_router, tags=["貼文"])
api_router.include_router(outfits_router, tags=["穿搭"])