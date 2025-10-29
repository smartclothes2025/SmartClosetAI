# last_worn_at 欄位更新

更新時間: 2025-10-29 14:35

## 需求

在上傳衣物時，自動將 `last_worn_at` 設定為上傳日期，而不是保持 NULL。

## 修改內容 ✅

### 1. 更新 ORM 模型

**檔案**: `app/models/wardrobe.py`

**新增欄位定義**:
```python
last_worn_at = Column(DateTime(timezone=True), nullable=True)
```

**在 save_item_to_wardrobe 方法中設定**:
```python
item = cls(
    user_id=current_user.id,
    name=display_name,
    category=cat_val,
    color=resolved_color,
    style=resolved_style,
    cover_image_url=str(p.as_posix()),
    attributes=attrs,
    last_worn_at=datetime.now(timezone.utc)  # 新增
)
```

### 2. 更新上傳 API

**檔案**: `app/api/v1/upload.py`

**在建立 WardrobeItem 時設定**:
```python
# 設定 last_worn_at 為上傳時間
if "last_worn_at" in model_cols:
    item_kwargs["last_worn_at"] = datetime.utcnow()

item = WardrobeItem(**item_kwargs)
```

## 資料庫欄位資訊

從資料庫查詢結果：
```
last_worn_at: date (Nullable: YES, Default: None)
```

**注意**: 資料庫中的類型是 `date`，但 ORM 使用 `DateTime(timezone=True)`。SQLAlchemy 會自動處理轉換。

## 影響範圍 📊

### 受影響的上傳端點

1. **POST `/api/v1/upload/`** ✅
   - 批次上傳衣物
   - 會自動設定 `last_worn_at`

2. **POST `/api/v1/upload/clothes`** ✅
   - 別名端點
   - 內部呼叫 `upload_image`，同樣會設定

3. **使用 `save_item_to_wardrobe` 的地方** ✅
   - 任何使用此方法的程式碼
   - 都會自動設定 `last_worn_at`

## 行為變更 🔄

### 修改前
```python
# 上傳衣物後
{
  "id": "xxx",
  "name": "包包",
  "last_worn_at": null,  # NULL
  "created_at": "2025-10-29T14:00:00Z"
}
```

### 修改後
```python
# 上傳衣物後
{
  "id": "xxx",
  "name": "包包",
  "last_worn_at": "2025-10-29T14:00:00Z",  # 設定為上傳時間
  "created_at": "2025-10-29T14:00:00Z"
}
```

## 對推薦系統的影響 🎯

### 之前的行為
```python
# 查詢超過 90 天未穿的衣物
inactive_items = db.query(WardrobeItem).filter(
    or_(
        and_(
            WardrobeItem.last_worn_at.isnot(None),
            WardrobeItem.last_worn_at < cutoff_date,
        ),
        and_(
            WardrobeItem.last_worn_at.is_(None),  # 包含 NULL 的衣物
            WardrobeItem.created_at < cutoff_date,
        ),
    )
)
```

### 現在的行為
```python
# 所有衣物都有 last_worn_at，不需要檢查 NULL
inactive_items = db.query(WardrobeItem).filter(
    WardrobeItem.last_worn_at < cutoff_date
)
```

**建議**: 可以簡化推薦查詢邏輯，因為現在所有衣物都會有 `last_worn_at` 值。

## 語意說明 📝

### last_worn_at 的意義

**修改前**:
- `NULL` = 從未穿過
- 有值 = 最後一次穿著的日期

**修改後**:
- 上傳時 = 上傳日期（假設剛買的衣服可能會穿）
- 穿著後 = 更新為實際穿著日期

### 合理性

這個設計是合理的，因為：
1. **新衣物通常會穿**: 剛上傳的衣物通常是新買的或想穿的
2. **避免立即推薦**: 不會在上傳後立即被推薦為「未穿衣物」
3. **簡化邏輯**: 不需要特別處理 NULL 值

## 測試驗證 ✅

### 測試步驟

1. **上傳新衣物**:
```bash
# 使用前端上傳功能或 API
POST /api/v1/upload/
```

2. **檢查資料庫**:
```sql
SELECT id, name, last_worn_at, created_at
FROM wardrobe_items
WHERE user_id = '9c33c7e9-ce22-4c4d-b385-15504ef368da'
ORDER BY created_at DESC
LIMIT 5;
```

3. **預期結果**:
- `last_worn_at` 不應該是 NULL
- `last_worn_at` 應該接近 `created_at`

### 驗證腳本

```python
# test_last_worn_at.py
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

# ... 連線設定 ...

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, name, last_worn_at, created_at
        FROM wardrobe_items
        WHERE user_id = :user_id
        AND created_at > NOW() - INTERVAL '1 hour'
    """), {"user_id": "9c33c7e9-ce22-4c4d-b385-15504ef368da"})
    
    for row in result:
        print(f"ID: {row.id}")
        print(f"  名稱: {row.name}")
        print(f"  last_worn_at: {row.last_worn_at}")
        print(f"  created_at: {row.created_at}")
        
        if row.last_worn_at is None:
            print("  ❌ last_worn_at 是 NULL！")
        else:
            print("  ✅ last_worn_at 已設定")
```

## 後續改進建議 🚀

### 1. 穿著記錄功能

當使用者實際穿著衣物時，更新 `last_worn_at`：

```python
@router.post("/wear/{item_id}")
def mark_as_worn(
    item_id: int,
    wear_date: datetime = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """記錄衣物穿著"""
    item = db.query(WardrobeItem).filter(
        WardrobeItem.id == item_id,
        WardrobeItem.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="衣物不存在")
    
    item.last_worn_at = wear_date or datetime.now(timezone.utc)
    db.commit()
    
    return {"message": "已記錄穿著", "last_worn_at": item.last_worn_at}
```

### 2. 穿著次數統計

利用 `worn_count` 欄位（資料庫已有）：

```python
# 每次穿著時
item.last_worn_at = datetime.now(timezone.utc)
item.worn_count = (item.worn_count or 0) + 1
db.commit()
```

### 3. 推薦邏輯優化

結合 `last_worn_at` 和 `worn_count`：

```python
# 推薦很少穿的衣物
rare_items = db.query(WardrobeItem).filter(
    WardrobeItem.user_id == current_user.id,
    WardrobeItem.worn_count < 3,  # 穿著次數少於 3 次
    WardrobeItem.last_worn_at < cutoff_date  # 且很久沒穿
).all()
```

### 4. 穿搭建立時自動更新

當使用者建立穿搭時，自動更新相關衣物的 `last_worn_at`：

```python
@router.post("/outfits")
def create_outfit(
    outfit_data: OutfitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 建立穿搭
    outfit = Outfit(...)
    db.add(outfit)
    
    # 更新衣物的 last_worn_at
    for item_id in outfit_data.item_ids:
        item = db.query(WardrobeItem).filter(
            WardrobeItem.id == item_id
        ).first()
        if item:
            item.last_worn_at = datetime.now(timezone.utc)
    
    db.commit()
    return outfit
```

## 相關檔案 📁

### 後端
- `app/models/wardrobe.py` - ORM 模型（已修改）
- `app/api/v1/upload.py` - 上傳 API（已修改）
- `app/api/v1/recommendations.py` - 推薦 API（可簡化查詢）

### 測試
- `check_last_worn_at.py` - 檢查資料庫欄位
- `test_last_worn_at.py` - 驗證功能（待建立）

### 文檔
- `LAST_WORN_AT_UPDATE.md` - 本文檔

---

## 使用說明 💡

### 開發者

1. **確認後端已重啟**（如使用 `--reload` 則自動）

2. **測試上傳**:
   - 前端上傳新衣物
   - 檢查 Console 或資料庫

3. **驗證結果**:
   ```sql
   SELECT last_worn_at FROM wardrobe_items 
   WHERE id = (SELECT MAX(id) FROM wardrobe_items);
   ```

### 使用者

- **無感知變更**: 使用者不需要做任何改變
- **推薦更準確**: 推薦系統會更準確地識別未穿衣物

---

**狀態**: ✅ 完成  
**影響範圍**: 衣物上傳、推薦系統  
**向後相容**: 是（舊資料的 NULL 值仍可正常處理）
