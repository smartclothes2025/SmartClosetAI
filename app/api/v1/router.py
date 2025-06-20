#api/v1/router.py
from fastapi import APIRouter
from .auth import router as auth_router
from .weather import router as weather_router
from .upload import router as upload_router
from .chat import router as chat_router
from .price_suggestion import router as price_suggestion_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["認證"])  
api_router.include_router(weather_router, prefix="/weather", tags=["天氣與穿搭"])
api_router.include_router(upload_router, prefix="/upload", tags=["上傳"])
api_router.include_router(chat_router, prefix="/chat", tags=["聊天"])
api_router.include_router(price_suggestion_router, prefix="/price-suggestion", tags=["估價"])