# 前端顯示推薦修復步驟

## 問題診斷 ✅

**問題**: 前端顯示「暫時沒有未穿的衣物」

**原因**: `/api/v1/recommendations/inactive` 端點使用 `updated_at` 而不是 `last_worn_at` 來查詢

**解決方案**: 已修改後端查詢邏輯使用 `last_worn_at`

## 已修復內容 ✅

### 後端修改

**檔案**: `app/api/v1/recommendations.py`

**修改前**:
```python
# 使用 updated_at
inactive_items = (
    db.query(WardrobeItem)
    .filter(WardrobeItem.updated_at < cutoff_date)
    .all()
)
```

**修改後**:
```python
# 使用 last_worn_at
inactive_items = (
    db.query(WardrobeItem)
    .filter(
        or_(
            and_(
                WardrobeItem.last_worn_at.isnot(None),
                WardrobeItem.last_worn_at < cutoff_date,
            ),
            and_(
                WardrobeItem.last_worn_at.is_(None),
                WardrobeItem.created_at < cutoff_date,
            ),
        )
    )
    .all()
)
```

### API 測試結果

```bash
GET /api/v1/recommendations/inactive?days=90
Status: 200

[{
  "item": {
    "id": "689b8d46-edf6-4b85-a00a-e9b2ea7d072d",
    "name": "帽子2",
    "imageUrl": "https://storage.googleapis.com/...",
    "category": "帽子",
    "color": "",
    "last_worn": "2025-07-21T00:00:00+00:00",
    "created_at": "2025-10-29T14:40:32+08:00",
    "daysInactive": 100
  },
  "suggestions": []
}]
```

## 前端刷新步驟 🔄

### 方法 1: 強制重新整理（推薦）

1. **開啟瀏覽器開發者工具**
   - 按 `F12` 或 `Ctrl + Shift + I`

2. **清除快取並重新整理**
   - 按 `Ctrl + Shift + R` (Windows/Linux)
   - 或按 `Cmd + Shift + R` (Mac)
   - 或在開發者工具的 Network 標籤中勾選 "Disable cache"

3. **重新載入頁面**

### 方法 2: 清除 SWR 快取

在瀏覽器 Console 執行：

```javascript
// 方法 1: 重新載入頁面
location.reload(true);

// 方法 2: 如果知道 mutate 函數，可以手動觸發重新請求
// (需要在組件內部)
```

### 方法 3: 清除瀏覽器快取

1. 按 `Ctrl + Shift + Delete` 開啟清除快取對話框
2. 選擇「快取的圖片和檔案」
3. 選擇時間範圍：「最近 1 小時」
4. 點擊「清除資料」
5. 重新整理頁面

## 預期結果 🎯

刷新後，你應該看到：

### 今日推薦區塊
```
┌─────────────────────────────────────┐
│ 推薦                90 天未穿·智慧搭配 │
├─────────────────────────────────────┤
│  [圖片]                              │
│  帽子2                               │
│  帽子 ·                              │
│  已 100 天未穿                       │
│                                     │
│  建議搭配                            │
│  [沒有共現資料...]                   │
└─────────────────────────────────────┘
```

### Console 輸出
```
🔍 fetchJSON Debug:
  URL: /api/v1/recommendations/inactive?days=90
  ✅ Using REAL API via proxy
  🔑 Added Authorization header with token
  Response status: 200
  ✅ Success, data length: 1
```

## 疑難排解 🔧

### 問題 1: 仍然看不到推薦

**檢查步驟**:

1. **確認登入狀態**:
```javascript
// 在 Console 執行
console.log('Token:', localStorage.getItem('token'));
console.log('User:', localStorage.getItem('user'));
```

應該顯示:
```
Token: user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token
User: {"id":"9c33c7e9-ce22-4c4d-b385-15504ef368da",...}
```

2. **檢查 Network 標籤**:
   - 開啟開發者工具 → Network 標籤
   - 重新整理頁面
   - 找到 `recommendations/inactive?days=90` 請求
   - 檢查 Status Code（應該是 200）
   - 檢查 Response（應該有資料）

3. **檢查 Headers**:
   - 在 Network 標籤中點擊該請求
   - 查看 Request Headers
   - 確認有 `Authorization: Bearer user-...` header

### 問題 2: 401 Unauthorized

**解決方案**: 重新登入

```javascript
// 清除舊資料
localStorage.clear();

// 重新整理頁面
location.reload();

// 使用訪客登入
```

### 問題 3: 顯示「載入失敗」

**可能原因**:
- 後端沒有運行
- 認證失敗
- 網路問題

**檢查步驟**:
1. 確認後端正在運行（檢查終端）
2. 測試 ping-db: `http://localhost:8000/api/v1/ping-db`
3. 檢查 Console 錯誤訊息

## 技術細節 📊

### 前端組件

**檔案**: `src/components/RecommendInactive.jsx`

**API 呼叫**:
```javascript
const { data, error, isLoading } = useSWR(
  `/api/v1/recommendations/inactive?days=90`,
  fetchJSON,
  { revalidateOnFocus: false }
);
```

### 資料流程

```
前端組件 
  → useSWR 呼叫 fetchJSON
  → fetchJSON 自動加上 Authorization header
  → 後端驗證 token
  → 查詢該使用者的 wardrobe_items (last_worn_at < 90天前)
  → 返回結果
  → 前端顯示推薦卡片
```

### 快取機制

SWR 會快取 API 回應，設定為：
- `revalidateOnFocus: false` - 不在焦點改變時重新驗證
- 預設快取時間：無限期（直到手動刷新或頁面重新載入）

## 驗證清單 ✓

刷新後，請確認：

- [ ] 看到推薦卡片（帽子2）
- [ ] 顯示「已 100 天未穿」
- [ ] 圖片正常載入
- [ ] Console 無錯誤訊息
- [ ] Network 標籤顯示 200 狀態碼
- [ ] 可以點擊關閉按鈕略過推薦

## 後續測試 🧪

### 測試其他天數

修改 URL 參數測試不同門檻：

```javascript
// 在 Console 執行
fetch('/api/v1/recommendations/inactive?days=30', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
})
.then(r => r.json())
.then(data => console.log('30天未穿:', data));

fetch('/api/v1/recommendations/inactive?days=60', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
})
.then(r => r.json())
.then(data => console.log('60天未穿:', data));
```

### 測試 /daily 端點

```javascript
fetch('/api/v1/recommendations/daily', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
})
.then(r => r.json())
.then(data => console.log('今日推薦:', data));
```

## 相關文檔 📁

- `RECOMMENDATIONS_FEATURE_SUMMARY.md` - 推薦功能完整文檔
- `DAILY_RECOMMENDATION_TEST_SUCCESS.md` - 後端測試報告
- `FRONTEND_AUTH_FIX.md` - 前端認證修復
- `FRONTEND_DISPLAY_FIX.md` - 本文檔

---

**修復狀態**: ✅ 完成  
**需要動作**: 前端強制刷新（Ctrl + Shift + R）  
**預期結果**: 顯示帽子2的推薦卡片
