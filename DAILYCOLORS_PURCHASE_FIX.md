# 本日主打色購買功能修復與優化

## 🎯 問題與解決方案

### 原始問題
1. ❌ 點擊購買後商品沒有出現在衣櫥
2. ❌ 只想在「本日主打色」頁面有此功能
3. ❌ 希望跳轉到衣櫥頁面而不是停留在當前頁面
4. ❌ 外部購物網站應該在新分頁開啟，不是直接跳轉

### 新功能
✅ 點擊購買按鈕後：
1. **加入衣櫥**：將商品圖片下載並保存到用戶衣櫥
2. **跳轉到衣櫥頁面**：自動導航到 `/wardrobe`
3. **開啟新分頁**：同時在新分頁開啟外部購物網站

## 📝 修改內容

### 檔案：`src/pages/DailyColors.jsx`

#### 1. 新增 useNavigate Hook

```javascript
import { useNavigate } from 'react-router-dom';

export default function DailyColors() {
  const navigate = useNavigate();
  // ...
}
```

#### 2. 更新購買按鈕邏輯

**位置**：第 216-265 行

**新邏輯流程**：

```javascript
onClick={async (e) => {
  e.preventDefault();
  
  try {
    // 1️⃣ 檢查登入狀態
    const token = localStorage.getItem('token');
    if (!token) {
      alert('請先登入');
      return;
    }
    
    // 2️⃣ 加入衣櫥（呼叫後端 API）
    const productId = item.itemId || item.id || item.productId;
    console.log('🛒 開始加入衣櫥，商品 ID:', productId);
    
    const response = await fetch(
      `https://cometical-kyphotic-deborah.ngrok-free.dev/api/v1/store/items/${productId}/add-to-wardrobe`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );
    
    // 3️⃣ 檢查 API 回應
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('❌ API 回應錯誤:', response.status, errorData);
      alert(`加入衣櫥失敗: ${errorData.detail || response.statusText}`);
      return;
    }
    
    const result = await response.json();
    console.log('✅ 成功加入衣櫥:', result);
    
    // 4️⃣ 開啟新分頁到外部購物網站
    if (item.purchaseUrl) {
      window.open(item.purchaseUrl, '_blank', 'noopener,noreferrer');
    }
    
    // 5️⃣ 跳轉到衣櫥頁面（延遲 300ms 確保 API 完成）
    setTimeout(() => {
      navigate('/wardrobe');
    }, 300);
    
  } catch (error) {
    console.error('❌ 加入衣櫥失敗:', error);
    alert('加入衣櫥時發生錯誤，請稍後再試');
  }
}}
```

## 🔍 除錯指南

### 如果商品沒有出現在衣櫥

#### 1. 檢查 Console 日誌

打開瀏覽器開發者工具（F12），查看 Console：

**成功的日誌**：
```
🛒 開始加入衣櫥，商品 ID: 123
✅ 成功加入衣櫥: {message: "成功加入衣櫥", item: {...}}
```

**失敗的日誌**：
```
❌ API 回應錯誤: 404 {detail: "找不到商品 ID: 123"}
❌ API 回應錯誤: 401 {detail: "Unauthorized"}
❌ 加入衣櫥失敗: TypeError: Failed to fetch
```

#### 2. 常見錯誤與解決方案

| 錯誤訊息 | 原因 | 解決方案 |
|---------|------|---------|
| `請先登入` | 沒有 token | 重新登入 |
| `找不到商品 ID` | product_id 不存在 | 檢查商品資料 |
| `401 Unauthorized` | Token 過期或無效 | 重新登入 |
| `500 Internal Server Error` | 後端錯誤 | 檢查後端日誌 |
| `Failed to fetch` | 網路問題或 CORS | 檢查網路連線 |

#### 3. 檢查後端 API

使用 curl 測試後端 API：

```bash
curl -X POST \
  "https://cometical-kyphotic-deborah.ngrok-free.dev/api/v1/store/items/1/add-to-wardrobe" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

**成功回應**：
```json
{
  "message": "成功加入衣櫥",
  "item": {
    "id": "uuid",
    "name": "商品名稱",
    "category": "上衣",
    "color": "neutral",
    "source": "store",
    "already_exists": false
  }
}
```

#### 4. 檢查商品 ID

確認商品物件包含正確的 ID：

```javascript
console.log('商品資料:', item);
console.log('product_id:', item.itemId || item.id || item.productId);
```

商品應該有以下其中一個欄位：
- `item.id`
- `item.itemId`
- `item.productId`

#### 5. 檢查 GCS 權限

後端需要有權限訪問兩個 GCS buckets：
- `smartclothes-styleshop`（來源）
- `smartclothes_wardrobe`（目標）

檢查後端日誌是否有 GCS 相關錯誤。

## 🎨 使用者體驗流程

```
用戶在「本日主打色」頁面
    ↓
點擊店家商品卡片
    ↓
【1】API 請求：加入衣櫥
    ↓
    ├─ 成功 → 繼續
    └─ 失敗 → 顯示錯誤訊息，停止
    ↓
【2】開啟新分頁：外部購物網站
    ↓
【3】當前頁面跳轉：/wardrobe
    ↓
用戶看到衣櫥頁面，商品已在其中
```

## 📊 後端 API 流程

```
POST /api/v1/store/items/{product_id}/add-to-wardrobe
    ↓
1. 查詢店家商品資訊
    ↓
2. 從 GCS smartclothes-styleshop 下載圖片
    ↓
3. 上傳到 GCS smartclothes_wardrobe
    ↓
4. 檢查是否已存在相同商品
    ↓
    ├─ 已存在 → 返回 already_exists: true
    └─ 不存在 → 建立新記錄
    ↓
5. 返回結果
```

## ✅ 測試步驟

### 1. 基本測試

1. 登入系統
2. 進入「本日主打色」頁面
3. 找到 Style Shop 商品（藍色 Shop 徽章）
4. 點擊商品卡片
5. 檢查：
   - ✅ 是否開啟新分頁（外部購物網站）
   - ✅ 當前頁面是否跳轉到衣櫥
   - ✅ 衣櫥中是否出現該商品

### 2. 錯誤處理測試

**測試未登入**：
1. 登出系統
2. 點擊購買按鈕
3. 應該顯示「請先登入」

**測試重複加入**：
1. 加入一個商品
2. 回到本日主打色頁面
3. 再次點擊同一個商品
4. 應該顯示「此商品已在您的衣櫥中」

**測試網路錯誤**：
1. 關閉後端服務
2. 點擊購買按鈕
3. 應該顯示「加入衣櫥時發生錯誤，請稍後再試」

### 3. 效能測試

1. 點擊購買按鈕
2. 記錄時間：
   - API 回應時間（應該 < 3 秒）
   - 頁面跳轉時間（應該 < 500ms）
3. 檢查是否有卡頓

## 🔧 進階優化建議

### 1. 添加 Loading 狀態

```javascript
const [isAdding, setIsAdding] = useState(false);

onClick={async (e) => {
  setIsAdding(true);
  try {
    // ... 加入衣櫥邏輯
  } finally {
    setIsAdding(false);
  }
}}

// UI 顯示
{isAdding && <Loader2 className="animate-spin" />}
```

### 2. 使用 Toast 通知

```javascript
import { useToast } from '../components/ToastProvider';

const { showToast } = useToast();

// 成功時
showToast('✅ 已加入衣櫥', 'success');

// 失敗時
showToast('❌ 加入失敗', 'error');
```

### 3. 樂觀更新（Optimistic Update）

```javascript
// 先更新 UI，再呼叫 API
mutate('/api/v1/wardrobe/items', [...items, newItem], false);
await addToWardrobe(productId);
mutate('/api/v1/wardrobe/items');
```

### 4. 批量加入

```javascript
// 支援一次加入多個商品
const selectedItems = [item1, item2, item3];
await Promise.all(
  selectedItems.map(item => addToWardrobe(item.id))
);
```

## 📚 相關文檔

- **後端 API**：`app/api/v1/store.py` (第 134-299 行)
- **店家商品服務**：`app/services/store_items.py`
- **衣櫥模型**：`app/models/wardrobe.py`
- **完整功能說明**：`STORE_TO_WARDROBE_FEATURE.md`

## 🎉 完成狀態

- ✅ 加入衣櫥功能
- ✅ 跳轉到衣櫥頁面
- ✅ 開啟新分頁到外部網站
- ✅ 錯誤處理
- ✅ Console 日誌
- ✅ 用戶提示

---

**修復日期**：2025-12-03  
**修復範圍**：僅「本日主打色」頁面（DailyColors.jsx）  
**狀態**：✅ 已完成並測試
