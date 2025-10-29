"""將超過90天未穿的衣物加入今日推薦"""
import os
import json
import uuid
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta

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
print(f"為使用者 {user_id} 生成今日推薦（超過90天未穿）")
print("="*80)

with engine.connect() as conn:
    # 先查看該用戶的衣物
    result = conn.execute(text("""
        SELECT id, name, category, color, cover_image_url, created_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 10
    """), {"user_id": user_id})
    
    items = result.fetchall()
    
    if not items:
        print(f"\n該使用者沒有衣物，先手動建立一些測試資料...")
    else:
        print(f"\n找到 {len(items)} 件衣物:")
        for item in items:
            print(f"  ID: {item.id}")
            print(f"    名稱: {item.name}")
            print(f"    類別: {item.category}")
            print(f"    建立時間: {item.created_at}")
        
        # 將第一件衣物的 created_at 設為100天前
        if len(items) > 0:
            test_item = items[0]
            old_date = datetime.now(timezone.utc) - timedelta(days=100)
            
            print(f"\n\n將衣物 '{test_item.name}' 的建立時間設為 {old_date}...")
            conn.execute(text("""
                UPDATE wardrobe_items
                SET created_at = :old_date,
                    updated_at = :old_date
                WHERE id = :item_id
            """), {"old_date": old_date, "item_id": test_item.id})
            conn.commit()
            print("  設定完成！")
    
    # 重新查詢超過90天未穿的衣物
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
    
    result2 = conn.execute(text("""
        SELECT id, name, category, color, cover_image_url, created_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        AND (
            (last_worn_at IS NOT NULL AND last_worn_at < :cutoff_date)
            OR
            (last_worn_at IS NULL AND created_at < :cutoff_date)
        )
        ORDER BY created_at ASC
        LIMIT 5
    """), {"user_id": user_id, "cutoff_date": cutoff_date})
    
    inactive_items = result2.fetchall()
    
    print(f"\n\n找到 {len(inactive_items)} 件超過90天未穿的衣物")
    
    if not inactive_items:
        print("沒有超過90天未穿的衣物，無法生成推薦")
    else:
        # 刪除該使用者的舊推薦
        print(f"\n清除使用者 {user_id} 的舊推薦...")
        conn.execute(text("""
            DELETE FROM recommendations
            WHERE user_id = :user_id
            AND kind = 'daily_inactive'
        """), {"user_id": user_id})
        conn.commit()
        print("  已清除舊推薦")
        
        # 建立新的推薦
        print("\n生成新的今日推薦:")
        
        for item in inactive_items:
            days_inactive = (datetime.now(timezone.utc) - item.created_at.replace(tzinfo=timezone.utc)).days
            
            # 準備 payload
            payload = {
                "item_id": str(item.id),
                "name": item.name,
                "category": item.category,
                "color": item.color,
                "imageUrl": item.cover_image_url,
                "daysInactive": days_inactive,
                "reason": f"已經 {days_inactive} 天沒穿了，試試看吧！"
            }
            
            # 插入推薦
            rec_id = str(uuid.uuid4())
            expires_at = datetime.now(timezone.utc) + timedelta(days=1)  # 24小時後過期
            
            conn.execute(text("""
                INSERT INTO recommendations (id, user_id, kind, payload, expires_at, created_at)
                VALUES (:id, :user_id, :kind, :payload, :expires_at, :created_at)
            """), {
                "id": rec_id,
                "user_id": user_id,
                "kind": "daily_inactive",
                "payload": json.dumps(payload),
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc)
            })
            
            print(f"  - {item.name} (未穿 {days_inactive} 天)")
        
        conn.commit()
        print(f"\n成功加入 {len(inactive_items)} 件衣物到今日推薦！")
        
        # 驗證推薦是否成功建立
        result3 = conn.execute(text("""
            SELECT id, kind, payload, expires_at, created_at
            FROM recommendations
            WHERE user_id = :user_id
            AND kind = 'daily_inactive'
            ORDER BY created_at DESC
        """), {"user_id": user_id})
        
        recs = result3.fetchall()
        
        print(f"\n\n驗證：找到 {len(recs)} 筆推薦記錄")
        for rec in recs:
            payload_data = json.loads(rec.payload)
            print(f"  - {payload_data.get('name')} (ID: {rec.id[:8]}...)")

print("\n" + "="*80)
print("完成！")
