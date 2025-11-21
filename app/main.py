# app/main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging, os, time
from app.api.v1.router import api_router
from app.core.config import settings
from sqlalchemy import create_engine
from dotenv import load_dotenv # 必須先安裝： pip install python-dotenv

engine = create_engine(settings.DATABASE_URL)

load_dotenv()

# 配置日誌格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SmartClosetAI API")

# 請求日誌中間件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # 記錄請求
    logger.info(f"🔵 收到請求: {request.method} {request.url.path}")
    
    # 處理請求
    response = await call_next(request)
    
    # 計算處理時間
    process_time = time.time() - start_time
    logger.info(f"✅ 完成請求: {request.method} {request.url.path} - 狀態碼: {response.status_code} - 耗時: {process_time:.2f}秒")
    
    return response

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
@app.get("/test-log")
async def test_log():
    # Uvicorn Worker ID (例如 43088) 會執行這個 print
    print("--- 收到 /test-log 請求！應用程式仍在執行 ---") 
    return {"status": "ok", "message": "Log test successful"}

@app.get("/")
def read_root():
    return {"message": "智慧衣櫃後端啟動成功 (僅使用 GCS 儲存)"}

# include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
