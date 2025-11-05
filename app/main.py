# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# ❌ 已移除本地 uploads 資料夾的靜態檔案掛載
# 所有圖片現在必須從 GCS 讀取

@app.get("/")
def read_root():
    return {"message": "智慧衣櫃後端啟動成功 (僅使用 GCS 儲存)"}

# include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
