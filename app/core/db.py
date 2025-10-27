# core/db.py
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base



# 1. 載入 .env
load_dotenv()

# 2. 讀環境變數並 strip() 去掉頭尾所有空白或不可見字元
PGUSER     = os.getenv("PGUSER",    "postgres").strip()
PGPASSWORD = os.getenv("PGPASSWORD", "cguim").strip()
PGHOST     = os.getenv("PGHOST",    "localhost").strip()
PGPORT     = os.getenv("PGPORT",    "5432").strip()
PGDATABASE = os.getenv("PGDATABASE","postgres").strip()

# 3. 對密碼做 URL 轉義
PGPASSWORD_QUOTED = quote_plus(PGPASSWORD)

# 4. 組成乾淨的連線字串
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{PGUSER}:{PGPASSWORD_QUOTED}"
    f"@{PGHOST}:{PGPORT}/{PGDATABASE}"
)

# 5. 建立 Engine、Base、SessionLocal
engine = create_engine(SQLALCHEMY_DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 6. 提供 get_db 給 FastAPI 注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
