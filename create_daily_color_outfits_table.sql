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

-- 確認建立成功
SELECT 'daily_color_outfits 資料表建立成功' AS status;
