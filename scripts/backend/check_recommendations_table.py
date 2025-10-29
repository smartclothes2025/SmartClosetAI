"""檢查 recommendations 表結構和內容"""
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

user_id = "9c33c7e9-ce22-4c4d-b385-15504ef368da"

print("="*80)
print("檢查 recommendations 表結構")
print("="*80)

with engine.connect() as conn:
    # 查看表結構
    result = conn.execute(text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'recommendations'
        ORDER BY ordinal_position
    """))
    
    print("\nrecommendations 表的欄位:")
    for col in result:
        print(f"  - {col.column_name}: {col.data_type} (Nullable: {col.is_nullable})")
    
    # 查看現有推薦
    print(f"\n查看使用者 {user_id} 的現有推薦:")
    result2 = conn.execute(text("""
        SELECT * FROM recommendations
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 10
    """), {"user_id": user_id})
    
    recs = result2.fetchall()
    if recs:
        print(f"\n找到 {len(recs)} 筆推薦:")
        for rec in recs:
            print(f"  ID: {rec.id}")
            for key in rec._mapping.keys():
                print(f"    {key}: {rec._mapping[key]}")
            print("-" * 60)
    else:
        print("\n⚠️ 該使用者目前沒有推薦記錄")
    
    # 查看該使用者的所有衣物
    print(f"\n查看使用者 {user_id} 的所有衣物:")
    result3 = conn.execute(text("""
        SELECT id, name, category, color, created_at, updated_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        ORDER BY created_at DESC
    """), {"user_id": user_id})
    
    items = result3.fetchall()
    if items:
        print(f"\n找到 {len(items)} 件衣物:")
        for item in items:
            print(f"  ID: {item.id}")
            print(f"    名稱: {item.name}")
            print(f"    類別: {item.category}")
            print(f"    顏色: {item.color}")
            print(f"    建立時間: {item.created_at}")
            print("-" * 60)
    else:
        print("\n⚠️ 該使用者目前沒有衣物")

print("\n" + "="*80)
