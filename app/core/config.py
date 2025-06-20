from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

# 載入 .env 文件
load_dotenv()

class Settings(BaseSettings):
    # 基本設置
    PROJECT_NAME: str = "Smart Wardrobe"
    API_V1_STR: str = "/api/v1"
    
    # 數據庫設置
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/smart_wardrobe")
    
    # JWT 設置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小時
    
    # OpenAI API 設置
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # 文件上傳設置
    UPLOAD_FOLDER: str = "uploaded_images"
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5MB
    
    class Config:
        case_sensitive = True

# 創建全局設置實例
settings = Settings()
