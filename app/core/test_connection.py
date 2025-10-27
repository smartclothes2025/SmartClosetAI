# test_connection.py
from database import conn  # or import get_cursor
import sys

try:
    cur = conn.cursor()
    cur.execute('SELECT NOW()')
    now = cur.fetchone()[0]
    print(f'✅ 連線成功，資料庫時間：{now}')
    cur.close()
except Exception as e:
    print('❌ 連線失敗：', e)
    sys.exit(1)
finally:
    conn.close()
