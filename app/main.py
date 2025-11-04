# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging, os
from app.api.v1.router import api_router
from app.core.config import settings
from sqlalchemy import create_engine
from dotenv import load_dotenv # 必須先安裝： pip install python-dotenv

engine = create_engine(settings.DATABASE_URL)

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SmartClosetAI API")

# CORS：開發環境允許所有來源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開發環境允許所有來源
    allow_credentials=False,  # 允許所有來源時必須設為 False
    allow_methods=["*"],
    allow_headers=["*"],
)


# 把 uploads 資料夾對外掛到 /uploads 與 /api/v1/uploads（兼容前端不同路徑）
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/api/v1/uploads", StaticFiles(directory="uploads"), name="api_v1_uploads")

@app.get("/")
def read_root():
    return {"message": "智慧衣櫃後端啟動成功"}

UPLOAD_DIR = "uploaded_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount(f"/{UPLOAD_DIR}", StaticFiles(directory=UPLOAD_DIR), name=UPLOAD_DIR)

# include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
