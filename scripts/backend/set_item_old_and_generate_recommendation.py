"""將一件衣物設為超過90天未穿，並生成今日推薦"""
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
print(f"為使用者 {user_id} 設定超過90天未穿的衣物並生成推薦")
print("="*80)

with engine.connect() as conn:
    # 1. 查詢該使用者的所有衣物
    result = conn.execute(text("""
        SELECT id, name, category, color, cover_image_url, created_at, last_worn_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 5
    """), {"user_id": user_id})
    
    items = result.fetchall()
    
    if not items:
        print("\n該使用者沒有衣物！")
        exit(1)
    
    print(f"\n找到 {len(items)} 件衣物:")
    for idx, item in enumerate(items, 1):
        print(f"\n{idx}. ID: {item.id}")
        print(f"   名稱: {item.name}")
        print(f"   類別: {item.category}")
        print(f"   顏色: {item.color}")
        print(f"   建立時間: {item.created_at}")
        print(f"   last_worn_at: {item.last_worn_at}")
    
    # 2. 選擇第一件衣物，設定為100天前
    target_item = items[0]
    old_date = datetime.now(timezone.utc) - timedelta(days=100)
    
    print(f"\n\n將衣物 '{target_item.name}' (ID: {target_item.id}) 設為100天前...")
    
    conn.execute(text("""
        UPDATE wardrobe_items
        SET last_worn_at = :old_date,
            updated_at = :old_date
        WHERE id = :item_id
    """), {"old_date": old_date, "item_id": target_item.id})
    conn.commit()
    
    print(f"  設定完成！last_worn_at = {old_date}")
    
    # 3. 清除該使用者的舊推薦
    print(f"\n清除使用者 {user_id} 的舊推薦...")
    conn.execute(text("""
        DELETE FROM recommendations
        WHERE user_id = :user_id
        AND kind = 'daily_inactive'
    """), {"user_id": user_id})
    conn.commit()
    print("  已清除舊推薦")
    
    # 4. 查詢超過90天未穿的衣物
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
    
    result2 = conn.execute(text("""
        SELECT id, name, category, color, cover_image_url, created_at, last_worn_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        AND (
            (last_worn_at IS NOT NULL AND last_worn_at < :cutoff_date)
            OR
            (last_worn_at IS NULL AND created_at < :cutoff_date)
        )
        ORDER BY last_worn_at ASC NULLS FIRST
        LIMIT 5
    """), {"user_id": user_id, "cutoff_date": cutoff_date})
    
    inactive_items = result2.fetchall()
    
    print(f"\n找到 {len(inactive_items)} 件超過90天未穿的衣物")
    
    if not inactive_items:
        print("沒有超過90天未穿的衣物，無法生成推薦")
    else:
        # 5. 為每件衣物建立推薦記錄
        print("\n生成新的今日推薦:")
        
        for item in inactive_items:
            # 計算未穿天數
            if item.last_worn_at:
                last_worn = item.last_worn_at if isinstance(item.last_worn_at, datetime) else datetime.combine(item.last_worn_at, datetime.min.time())
                if last_worn.tzinfo is None:
                    last_worn = last_worn.replace(tzinfo=timezone.utc)
                days_inactive = (datetime.now(timezone.utc) - last_worn).days
            else:
                created = item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)
                days_inactive = (datetime.now(timezone.utc) - created).days
            
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
                VALUES (:id, :user_id, :kind, CAST(:payload AS jsonb), :expires_at, :created_at)
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
        
        # 6. 驗證推薦是否成功建立
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
            payload_data = rec.payload if isinstance(rec.payload, dict) else json.loads(rec.payload)
            rec_id_str = str(rec.id)
            print(f"  - {payload_data.get('name')} (ID: {rec_id_str[:8]}...)")
            print(f"    原因: {payload_data.get('reason')}")
            print(f"    過期時間: {rec.expires_at}")

print("\n" + "="*80)
print("完成！現在可以測試前端的今日推薦功能了")
print("API 端點: GET /api/v1/recommendations/daily")
print("="*80)
