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

print("資料庫 category_enum 允許值:")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT enumlabel 
        FROM pg_type t 
        JOIN pg_enum e ON t.oid = e.enumtypid  
        WHERE t.typname = 'category_enum'
        ORDER BY e.enumsortorder
    """))
    
    for row in result:
        print(f"  {row.enumlabel}")
