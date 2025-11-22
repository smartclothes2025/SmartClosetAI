"""
建立 daily_color_outfits 資料表
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 從環境變數獲取資料庫連線
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ 錯誤：未設定 DATABASE_URL 環境變數")
    exit(1)

print(f"📊 連接資料庫...")
engine = create_engine(DATABASE_URL)

# SQL 建立表格
sql = """
-- 建立 daily_color_outfits 資料表
CREATE TABLE IF NOT EXISTS daily_color_outfits (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    gender VARCHAR(10) NOT NULL,
    color_family VARCHAR(20) NOT NULL,
    is_main_color BOOLEAN DEFAULT FALSE,
    outfits_json JSONB NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 建立索引以提升查詢效能
CREATE INDEX IF NOT EXISTS idx_daily_color_outfits_date_gender 
ON daily_color_outfits (date, gender);

CREATE INDEX IF NOT EXISTS idx_daily_color_outfits_color_family 
ON daily_color_outfits (color_family);

CREATE INDEX IF NOT EXISTS idx_daily_color_outfits_is_main_color 
ON daily_color_outfits (is_main_color);
"""

try:
    with engine.connect() as conn:
        # 執行 SQL
        conn.execute(text(sql))
        conn.commit()
        print("✅ daily_color_outfits 資料表建立成功！")
        
        # 確認表格存在
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'daily_color_outfits'
        """))
        
        if result.fetchone():
            print("✅ 確認：資料表已存在於資料庫中")
        else:
            print("⚠️ 警告：無法確認資料表是否建立成功")
            
except Exception as e:
    print(f"❌ 錯誤：{e}")
    exit(1)

print("\n🎉 完成！現在可以重新啟動後端服務")
