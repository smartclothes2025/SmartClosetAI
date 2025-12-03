# 品牌合作商品加入衣櫥功能指南

## 功能概述

當用戶點擊品牌合作頁面的「購買」按鈕時，系統會：
1. **立即開啟外部購買連結**（跳轉到 Style Shop）
2. **同時將商品圖片加入用戶衣櫥**（背景自動處理）

## 技術架構

### 後端 API

**端點：** `POST /api/v1/store/items/{product_id}/add-to-wardrobe`

**功能流程：**
1. 根據 `product_id` 查詢店家商品資訊
2. 從 GCS `smartclothes-styleshop` bucket 下載商品圖片
3. 上傳到用戶衣櫥 GCS `smartclothes_wardrobe` bucket
4. 建立衣櫥資料庫記錄

**請求：**
```http
POST /api/v1/store/items/1/add-to-wardrobe
Authorization: Bearer {token}
```

**成功回應（新增）：**
```json
{
  "message": "成功加入衣櫥",
  "item": {
    "id": "123",
    "name": "女生灰T恤（通勤）",
    "category": "上衣",
    "color": "neutral",
    "img": "gs://smartclothes_wardrobe/wardrobe/1/tops/store_1.jpg",
    "source": "store",
    "product_id": 1,
    "already_exists": false
  }
}
```

**成功回應（已存在）：**
```json
{
  "message": "此商品已在您的衣櫥中",
  "item": {
    "id": "123",
    "name": "女生灰T恤（通勤）",
    "category": "上衣",
    "color": "neutral",
    "img": "gs://smartclothes_wardrobe/wardrobe/1/tops/store_1.jpg",
    "source": "store",
    "already_exists": true
  }
}
```

**錯誤回應：**
```json
{
  "detail": "找不到商品 ID: 999"
}
```

### GCS 路徑結構

**店家商品來源：**
```
gs://smartclothes-styleshop/styleshop/{gender}/{category}/{filename}
```

**用戶衣櫥目標：**
```
gs://smartclothes_wardrobe/wardrobe/{user_id}/{category}/store_{product_id}.jpg
```

**範例：**
- 來源：`gs://smartclothes-styleshop/styleshop/women/上衣/女生灰T恤（通勤）.png`
- 目標：`gs://smartclothes_wardrobe/wardrobe/1/tops/store_1.jpg`

### 資料庫記錄

新增的衣櫥商品會包含以下資訊：
- `name`: 商品名稱
- `category`: 類別（上衣、褲子等）
- `color`: 色系（neutral、khaki、blue、pink、green）
- `cover_image_url`: GCS 圖片 URL
- `tags`: `["品牌合作", "Style Shop"]`
- `attributes`: `{"source": "store", "product_id": 1}`
- `brand`: "Style Shop"

## 前端整合

### 方法 1：React 組件

```jsx
import React from 'react';

async function addStoreItemToWardrobe(productId, token) {
  const response = await fetch(
    `http://localhost:8000/api/v1/store/items/${productId}/add-to-wardrobe`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    }
  );
  
  if (!response.ok) {
    throw new Error('加入衣櫥失敗');
  }
  
  return await response.json();
}

function StoreItemCard({ item, token }) {
  const handlePurchaseClick = async () => {
    try {
      // 1. 立即開啟外部連結
      window.open(item.purchaseUrl, '_blank');
      
      // 2. 同時加入衣櫥
      const result = await addStoreItemToWardrobe(item.id, token);
      
      // 3. 顯示通知
      if (result.item.already_exists) {
        alert('此商品已在您的衣櫥中');
      } else {
        alert(`${result.item.name} 已加入衣櫥`);
      }
    } catch (error) {
      console.error('加入衣櫥失敗:', error);
      alert('加入衣櫥失敗，請稍後再試');
    }
  };
  
  return (
    <div className="store-item-card">
      <img src={item.imageUrl} alt={item.name} />
      <h3>{item.name}</h3>
      <button onClick={handlePurchaseClick}>
        購買並加入衣櫥
      </button>
    </div>
  );
}

export default StoreItemCard;
```

### 方法 2：原生 JavaScript

```html
<!DOCTYPE html>
<html>
<head>
  <title>品牌合作</title>
</head>
<body>
  <div class="store-item">
    <img src="https://..." alt="女生灰T恤（通勤）">
    <h3>女生灰T恤（通勤）</h3>
    <button 
      class="purchase-button"
      data-product-id="1"
      data-purchase-url="https://styleshop-delta.vercel.app/product-detail.html?id=1"
    >
      購買並加入衣櫥
    </button>
  </div>

  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const buttons = document.querySelectorAll('.purchase-button');
      
      buttons.forEach(button => {
        button.addEventListener('click', async () => {
          const productId = button.dataset.productId;
          const purchaseUrl = button.dataset.purchaseUrl;
          const token = localStorage.getItem('authToken');
          
          if (!token) {
            alert('請先登入');
            return;
          }
          
          try {
            // 1. 開啟外部連結
            window.open(purchaseUrl, '_blank');
            
            // 2. 加入衣櫥
            const response = await fetch(
              `http://localhost:8000/api/v1/store/items/${productId}/add-to-wardrobe`,
              {
                method: 'POST',
                headers: {
                  'Authorization': `Bearer ${token}`,
                  'Content-Type': 'application/json',
                },
              }
            );
            
            const result = await response.json();
            
            if (result.item.already_exists) {
              alert('此商品已在您的衣櫥中');
            } else {
              alert(`${result.item.name} 已加入衣櫥`);
            }
          } catch (error) {
            console.error('加入衣櫥失敗:', error);
            alert('加入衣櫥失敗，請稍後再試');
          }
        });
      });
    });
  </script>
</body>
</html>
```

### 方法 3：使用 Toast 通知（推薦）

```jsx
import { toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

async function handlePurchaseAndAddToWardrobe(productId, purchaseUrl, token) {
  try {
    // 1. 開啟外部連結
    window.open(purchaseUrl, '_blank');
    
    // 2. 顯示載入中
    const toastId = toast.loading('正在加入衣櫥...');
    
    // 3. 加入衣櫥
    const response = await fetch(
      `http://localhost:8000/api/v1/store/items/${productId}/add-to-wardrobe`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );
    
    const result = await response.json();
    
    // 4. 更新 toast
    if (result.item.already_exists) {
      toast.update(toastId, {
        render: '此商品已在您的衣櫥中',
        type: 'info',
        isLoading: false,
        autoClose: 3000,
      });
    } else {
      toast.update(toastId, {
        render: `${result.item.name} 已加入衣櫥`,
        type: 'success',
        isLoading: false,
        autoClose: 3000,
      });
    }
  } catch (error) {
    console.error('加入衣櫥失敗:', error);
    toast.error('加入衣櫥失敗，請稍後再試');
  }
}
```

## 使用場景

### 場景 1：本日主打色頁面

用戶瀏覽本日主打色，看到店家商品：
1. 點擊「購買」按鈕
2. 跳轉到 Style Shop 商品詳細頁
3. 商品自動加入用戶衣櫥
4. 顯示「已加入衣櫥」通知

### 場景 2：今日推薦頁面

用戶查看今日推薦穿搭，包含店家商品：
1. 點擊店家商品的「購買」按鈕
2. 跳轉到 Style Shop
3. 商品自動加入衣櫥
4. 下次可以直接在衣櫥中使用該商品

### 場景 3：重複加入

用戶已經加入過某商品，再次點擊購買：
1. 跳轉到 Style Shop（正常）
2. 系統檢測到商品已存在
3. 顯示「此商品已在您的衣櫥中」
4. 不會重複建立記錄

## 優勢

1. **無縫體驗**：用戶只需點擊一次，同時完成購買跳轉和加入衣櫥
2. **自動化**：無需手動上傳圖片，系統自動從 GCS 複製
3. **防重複**：自動檢測已存在的商品，避免重複加入
4. **標記來源**：商品會標記為「品牌合作」和「Style Shop」，方便管理
5. **即時反饋**：使用 toast 通知，用戶清楚知道操作結果

## 測試步驟

### 1. 測試 API

```bash
# 使用 curl 測試
curl -X POST "http://localhost:8000/api/v1/store/items/1/add-to-wardrobe" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### 2. 測試前端

1. 在品牌合作頁面找到任一商品
2. 點擊「購買」按鈕
3. 確認：
   - 外部連結有開啟
   - 顯示「已加入衣櫥」通知
   - 衣櫥中出現該商品

### 3. 測試重複加入

1. 對同一商品再次點擊「購買」
2. 確認：
   - 外部連結有開啟
   - 顯示「此商品已在您的衣櫥中」
   - 衣櫥中沒有重複記錄

## 注意事項

1. **認證 Token**：確保用戶已登入，有有效的 Bearer Token
2. **GCS 權限**：確保後端有權限讀取 `smartclothes-styleshop` 和寫入 `smartclothes_wardrobe`
3. **錯誤處理**：網路錯誤或 API 失敗時，要顯示友善的錯誤訊息
4. **效能**：API 調用是非阻塞的，不會影響外部連結的開啟速度

## 未來擴展

1. **批次加入**：支援一次加入多個商品
2. **購買記錄**：記錄用戶的購買行為
3. **推薦優化**：根據加入衣櫥的商品優化推薦演算法
4. **社群分享**：分享已購買的商品到社群

## 相關檔案

- **後端 API**：`app/api/v1/store.py`
- **店家商品服務**：`app/services/store_items.py`
- **衣櫥模型**：`app/models/wardrobe.py`
- **前端範例**：`frontend_add_to_wardrobe_example.js`
- **本指南**：`ADD_TO_WARDROBE_GUIDE.md`

## 技術支援

如有問題，請檢查：
1. 後端日誌：查看 `[add-to-wardrobe]` 相關日誌
2. 網路請求：使用瀏覽器開發者工具檢查 API 請求
3. GCS 權限：確認服務帳號有正確的權限設定
