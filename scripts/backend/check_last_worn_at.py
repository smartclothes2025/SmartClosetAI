"""檢查 wardrobe_items 表中是否有 last_worn_at 欄位"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

load_dotenv()

PGUSER = os.getenv("PGUSER", "postgres").strip()
PGPASSWORD = os.getenv("PGPASSWORD", "cguim").strip()
PGHOST = os.getenv("PGHOST", "localhost").strip()
PGPORT = os.getenv("PGPORT", "5432").strip()
PGDATABASE = os.getenv("PGDATABASE", "closet").strip()

PGPASSWORD_QUOTED = quote_plus(PGPASSWORD)
DATABASE_URL = f"postgresql://{PGUSER}:{PGPASSWORD_QUOTED}@{PGHOST}:{PGPORT}/{PGDATABASE}"

engine = create_engine(DATABASE_URL)

print("="*80)
print("檢查 wardrobe_items 表結構")
print("="*80)

with engine.connect() as conn:
    # 查看所有欄位
    result = conn.execute(text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'wardrobe_items'
        ORDER BY ordinal_position
    """))
    
    print("\nwardrobe_items 表的所有欄位:")
    has_last_worn = False
    for col in result:
        print(f"  - {col.column_name}: {col.data_type} (Nullable: {col.is_nullable}, Default: {col.column_default})")
        if col.column_name == 'last_worn_at':
            has_last_worn = True
    
    if has_last_worn:
        print("\n✅ 表中已有 last_worn_at 欄位")
    else:
        print("\n❌ 表中沒有 last_worn_at 欄位，需要新增")

print("\n" + "="*80)
