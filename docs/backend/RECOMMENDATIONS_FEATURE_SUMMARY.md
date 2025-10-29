# 今日推薦功能完成報告

完成時間: 2025-10-29 14:00

## 功能概述 📋

實作了**基於使用者的個人化今日推薦系統**，推薦超過 90 天未穿的衣物，鼓勵使用者重新利用衣櫃中的單品。

## 核心特性 ✨

### 1. **使用者隔離** 🔒
- 每個使用者只能看到自己的推薦
- 使用 Bearer Token 認證（格式：`user-{uuid}-token`）
- 自動過濾不屬於該使用者的衣物

### 2. **今日推薦生成** 📅
- 推薦超過 90 天未穿（未更新）的衣物
- 儲存在 `recommendations` 表中
- 推薦類型：`daily_inactive`
- 自動包含推薦原因（如：「已經 99 天沒穿了，試試看吧！」）

### 3. **推薦過期機制** ⏰
- 推薦有效期：24 小時
- 過期後自動過濾，不會顯示

## API 端點 🔌

### 1. GET `/api/v1/recommendations/daily`
**取得今日推薦（基於超過90天未穿的衣物）**

**需要認證**: ✅ 是

**Headers**:
```
Authorization: Bearer user-{uuid}-token
```

**Response 200**:
```json
[
  {
    "id": "recommendation-uuid",
    "item": {
      "id": "item-uuid",
      "name": "包包",
      "category": "包包",
      "color": "",
      "imageUrl": "https://...",
      "daysInactive": 99
    },
    "reason": "已經 99 天沒穿了，試試看吧！",
    "suggestions": []
  }
]
```

### 2. GET `/api/v1/recommendations/inactive?days=90`
**取得超過指定天數未穿的衣物清單**

**需要認證**: ✅ 是

**Query Parameters**:
- `days`: 未穿天數門檻（預設 90，範圍 1-365）

**Response 200**:
```json
[
  {
    "item": {
      "id": "item-uuid",
      "name": "包包",
      "imageUrl": "https://...",
      "category": "包包",
      "color": "",
      "last_worn": "2025-07-21T06:00:47.998030+00:00",
      "created_at": "2025-07-21T06:00:47.998030+00:00",
      "daysInactive": 99
    },
    "suggestions": []
  }
]
```

## 資料庫結構 💾

### recommendations 表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | UUID | 推薦 ID（主鍵）|
| user_id | UUID | 使用者 ID |
| kind | TEXT | 推薦類型（`daily_inactive`）|
| payload | JSONB | 推薦內容（JSON 格式）|
| expires_at | TIMESTAMP | 過期時間 |
| created_at | TIMESTAMP | 建立時間 |

### payload 結構

```json
{
  "item_id": "uuid",
  "name": "衣物名稱",
  "category": "類別",
  "color": "顏色",
  "imageUrl": "圖片URL",
  "daysInactive": 天數,
  "reason": "推薦原因"
}
```

## 實作細節 🔧

### 認證機制

**檔案**: `app/api/v1/recommendations.py`

```python
def current_user_from_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_strict),
    db: Session = Depends(get_db),
) -> User:
    """從 Authorization Bearer 取得當前用戶"""
    token = credentials.credentials
    
    # 解析 user-{uuid}-token 格式
    user_id = token[len("user-"):-len("-token")]
    
    # 驗證並查詢使用者
    user = db.query(User).filter(User.id == user_id).first()
    return user
```

### 推薦生成邏輯

**檔案**: `add_inactive_to_recommendations.py`

```python
# 1. 查詢超過 90 天未穿的衣物
cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)

inactive_items = db.execute(text("""
    SELECT id, name, category, color, cover_image_url, created_at
    FROM wardrobe_items
    WHERE user_id = :user_id
    AND created_at < :cutoff_date
"""), {"user_id": user_id, "cutoff_date": cutoff_date})

# 2. 為每件衣物建立推薦記錄
for item in inactive_items:
    payload = {
        "item_id": str(item.id),
        "name": item.name,
        "daysInactive": days_inactive,
        "reason": f"已經 {days_inactive} 天沒穿了，試試看吧！"
    }
    
    # 插入推薦，24小時後過期
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    
    db.execute(text("""
        INSERT INTO recommendations (id, user_id, kind, payload, expires_at)
        VALUES (:id, :user_id, 'daily_inactive', :payload, :expires_at)
    """))
```

### 推薦查詢邏輯

```python
# 查詢該使用者的有效推薦
result = db.execute(text("""
    SELECT id, kind, payload, expires_at, created_at
    FROM recommendations
    WHERE user_id = :user_id
    AND kind = 'daily_inactive'
    AND (expires_at IS NULL OR expires_at > NOW())
    ORDER BY created_at DESC
"""))
```

## 測試結果 ✅

### 測試使用者
- **User ID**: `9c33c7e9-ce22-4c4d-b385-15504ef368da`
- **Token**: `user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token`

### 測試腳本
```bash
python test_daily_recommendations.py
```

### 測試結果
```
1. GET /api/v1/recommendations/daily
   狀態碼: 200
   找到 1 筆推薦:
   - 包包 (類別: 包包, 未穿 99 天)

2. GET /api/v1/recommendations/inactive?days=90
   狀態碼: 200
   找到 0 件超過90天未穿的衣物
```

## 使用流程 🔄

### 1. 生成推薦（管理員/定時任務）

```bash
# 執行推薦生成腳本
python add_inactive_to_recommendations.py
```

這會：
1. 查詢該使用者超過 90 天未穿的衣物
2. 清除該使用者的舊推薦
3. 為每件衣物建立新的推薦記錄
4. 設定 24 小時過期時間

### 2. 前端取得推薦

```javascript
// 使用 Authorization Bearer Token
const response = await fetch('/api/v1/recommendations/daily', {
  headers: {
    'Authorization': `Bearer user-${userId}-token`
  }
});

const recommendations = await response.json();
```

### 3. 顯示推薦

前端接收到推薦後：
1. 顯示衣物圖片、名稱、類別
2. 顯示未穿天數和推薦原因
3. 可選：顯示搭配建議

## 可擴展功能 🚀

### 1. 搭配建議
在 `suggestions` 欄位中加入搭配的其他衣物：
```json
{
  "suggestions": [
    {"id": "xxx", "name": "褲子", "imageUrl": "..."},
    {"id": "yyy", "name": "上衣", "imageUrl": "..."}
  ]
}
```

### 2. 定時任務
使用 Celery 或 APScheduler 每天自動生成推薦：
```python
@scheduler.scheduled_job('cron', hour=6)  # 每天早上 6 點
def generate_daily_recommendations():
    # 為所有使用者生成推薦
    pass
```

### 3. 推薦多樣化
- 基於天氣推薦
- 基於穿著頻率推薦
- 基於使用者風格偏好推薦
- 基於場合推薦

### 4. 推薦反饋
記錄使用者是否採用推薦：
```sql
CREATE TABLE recommendation_feedback (
  id UUID PRIMARY KEY,
  recommendation_id UUID,
  user_id UUID,
  action TEXT,  -- 'accepted', 'rejected', 'ignored'
  created_at TIMESTAMP
);
```

### 5. 推薦演算法優化
- 使用機器學習預測使用者偏好
- 考慮季節因素
- 考慮流行趨勢

## 相關檔案 📁

### 後端
- `app/api/v1/recommendations.py` - 推薦 API 端點
- `app/models/wardrobe.py` - 衣物模型
- `app/models/auth.py` - 使用者模型

### 測試與工具
- `add_inactive_to_recommendations.py` - 生成推薦腳本
- `test_daily_recommendations.py` - API 測試腳本
- `check_user_inactive_items.py` - 檢查使用者衣物
- `check_recommendations_table.py` - 檢查推薦表結構

### 文檔
- `RECOMMENDATIONS_FEATURE_SUMMARY.md` - 本文檔

## 安全性考量 🔐

1. **認證**: 所有端點都需要 Bearer Token
2. **使用者隔離**: 自動過濾，確保使用者只能看到自己的資料
3. **SQL 注入防護**: 使用參數化查詢
4. **過期機制**: 推薦自動過期，避免資料堆積

## 效能優化建議 ⚡

1. **建立索引**:
```sql
CREATE INDEX idx_recommendations_user_kind 
ON recommendations(user_id, kind, expires_at);

CREATE INDEX idx_wardrobe_items_user_updated 
ON wardrobe_items(user_id, updated_at);
```

2. **快取**: 使用 Redis 快取熱門推薦
3. **批次處理**: 定時批次生成所有使用者的推薦
4. **分頁**: 如果推薦很多，加入分頁機制

---

## 使用範例 💡

### cURL 測試

```bash
# 取得今日推薦
curl -H "Authorization: Bearer user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token" \
  http://localhost:8000/api/v1/recommendations/daily

# 取得超過90天未穿的衣物
curl -H "Authorization: Bearer user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token" \
  "http://localhost:8000/api/v1/recommendations/inactive?days=90"
```

### Python 測試

```python
import requests

user_id = "9c33c7e9-ce22-4c4d-b385-15504ef368da"
token = f"user-{user_id}-token"

headers = {"Authorization": f"Bearer {token}"}

# 取得今日推薦
response = requests.get(
    "http://localhost:8000/api/v1/recommendations/daily",
    headers=headers
)

recommendations = response.json()
print(f"找到 {len(recommendations)} 筆推薦")
```

---

**狀態**: ✅ 完成並測試通過  
**版本**: 1.0  
**最後更新**: 2025-10-29
