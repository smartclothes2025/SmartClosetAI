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
from .recommendations import router as recommendations_router
from .notifications import router as notifications_router
from .search import router as search_router
from .virtual_fitting import router as fitting_router
from app.api.v1.endpoints import media


api_router = APIRouter()

# —— 新增這支跳過 DB 的假 endpoint ——
@api_router.get("/ping-db")
async def ping_db():
    return {"db_ping": "2025-08-02T12:00:00"}

api_router.include_router(auth_router, prefix="/auth", tags=["validation"])
api_router.include_router(weather_router, prefix="/weather", tags=["weather"])
api_router.include_router(upload_router, prefix="/upload", tags=["upload"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(price_suggestion_router, prefix="/price-suggestion", tags=["price-suggestion"])
api_router.include_router(clothes_router, prefix="/clothes", tags=["clothes"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(posts_router, prefix="/posts", tags=["post"])
api_router.include_router(outfits_router, tags=["outfit"])
api_router.include_router(recommendations_router, tags=["recommendation"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notification"])
api_router.include_router(search_router, prefix="/search", tags=["search"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(fitting_router, prefix="/fitting", tags=["fitting"])



