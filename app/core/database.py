# database.py
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('PGHOST'),
    port=os.getenv('PGPORT'),
    user=os.getenv('PGUSER'),
    password=os.getenv('PGPASSWORD'),
    dbname=os.getenv('PGDATABASE'),
    sslmode=os.getenv('PGSSLMODE', 'disable')
)

def get_cursor():
    return conn.cursor()

def close():
    conn.close()