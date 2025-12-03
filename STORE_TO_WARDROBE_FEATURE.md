# 店家商品一鍵購買並加入衣櫥功能

## 📋 功能概述

當用戶點擊「購買」按鈕時，系統會同時執行兩個動作：
1. **跳轉到外部連結**：開啟 Style Shop 商品詳細頁
2. **自動加入衣櫥**：將商品圖片從 GCS 下載並保存到用戶衣櫥

## 🎯 實作位置

### 後端 API

**檔案：** `app/api/v1/store.py`

**端點：** `POST /api/v1/store/items/{product_id}/add-to-wardrobe`

**功能流程：**
1. 根據 `product_id` 查詢店家商品資訊
2. 從 GCS `smartclothes-styleshop` bucket 下載商品圖片
3. 上傳到用戶衣櫥 GCS `smartclothes_wardrobe` bucket
4. 建立衣櫥資料庫記錄（`WardrobeItem`）

**GCS 路徑結構：**
```
來源（店家）：
gs://smartclothes-styleshop/styleshop/{gender}/{category}/{filename}

目標（衣櫥）：
gs://smartclothes_wardrobe/wardrobe/{user_id}/{category}/store_{product_id}.jpg
```

**回傳格式：**
```json
{
  "message": "成功加入衣櫥",
  "item": {
    "id": "uuid",
    "name": "商品名稱",
    "category": "上衣",
    "color": "neutral",
    "img": "gs://...",
    "source": "store",
    "product_id": 1,
    "already_exists": false
  }
}
```

**防重複機制：**
- 檢查是否已存在相同名稱和類別的商品
- 如果已存在，返回 `already_exists: true`

### 前端整合

已更新以下 4 個組件：

#### 1. **TodayRecommend.jsx** （今日推薦）
- 位置：第 200-235 行
- 購買按鈕同時跳轉和保存

#### 2. **OutfitProposal.jsx** （本日主打色 - 穿搭推薦）
- 位置：第 251-285 行
- 購買按鈕同時跳轉和保存

#### 3. **DailyColors.jsx** （本日主打色 - 商品卡片）
- 位置：第 211-262 行
- 整張卡片點擊同時跳轉和保存
- 提示文字改為「購買並加入衣櫥 →」

#### 4. **RecommendInactive.jsx** （今日推薦 - 久未穿衣物）
- 位置：第 157-192 行
- 購買按鈕同時跳轉和保存
- Tooltip 改為「購買並加入衣櫥」

## 🔧 技術細節

### 前端實作邏輯

```javascript
onClick={async () => {
  // 1. 跳轉到外部連結
  window.open(item.purchaseUrl, '_blank');
  
  // 2. 同時加入衣櫥
  try {
    const token = localStorage.getItem('token');
    if (!token) return;
    
    const productId = item.itemId || item.id || item.productId;
    const response = await fetch(
      `https://cometical-kyphotic-deborah.ngrok-free.dev/api/v1/store/items/${productId}/add-to-wardrobe`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      }
    );
    
    if (response.ok) {
      const result = await response.json();
      console.log('✅ 已加入衣櫥:', result);
    }
  } catch (error) {
    console.error('❌ 加入衣櫥失敗:', error);
  }
}}
```

### 後端核心邏輯

```python
@router.post("/items/{product_id}/add-to-wardrobe")
async def add_store_item_to_wardrobe(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. 查詢店家商品
    store_item = find_store_item_by_id(product_id)
    
    # 2. 下載圖片
    image_bytes = requests.get(store_item["imageUrl"]).content
    
    # 3. 上傳到用戶衣櫥 GCS
    gcs_path = f"wardrobe/{user_id}/{category}/store_{product_id}.jpg"
    cover_url = upload_file_to_gcs(image_bytes, gcs_path)
    
    # 4. 檢查是否已存在
    existing = db.query(WardrobeItem).filter(...).first()
    if existing:
        return {"message": "此商品已在您的衣櫥中", ...}
    
    # 5. 建立衣櫥記錄
    wardrobe_item = WardrobeItem(
        user_id=current_user.id,
        name=store_item["name"],
        category=category_enum,
        cover_image_url=cover_url,
        tags=["品牌合作", "Style Shop"],
        attributes={"source": "store", "product_id": product_id},
    )
    db.add(wardrobe_item)
    db.commit()
    
    return {"message": "成功加入衣櫥", ...}
```

## 📊 資料庫結構

### WardrobeItem 欄位

```python
- id: UUID (主鍵)
- user_id: UUID (外鍵)
- name: String (商品名稱)
- category: CategoryEnum (類別)
- color: String (色系)
- cover_image_url: String (GCS URI)
- tags: List[String] (["品牌合作", "Style Shop"])
- attributes: JSONB ({"source": "store", "product_id": 1})
- brand: String ("Style Shop")
- last_worn_at: DateTime (加入時間)
```

## 🎨 使用者體驗

### 視覺提示

1. **來源徽章**：
   - 店家商品：藍色「Shop」徽章
   - 衣櫥商品：綠色「衣櫃」徽章

2. **按鈕文字**：
   - 「購買」→ 點擊後跳轉 + 保存
   - 「購買並加入衣櫥 →」（DailyColors 頁面）

3. **Tooltip 提示**：
   - 「購買並加入衣櫥「商品名稱」」

### 操作流程

```
用戶點擊「購買」按鈕
    ↓
立即開啟新分頁（Style Shop 商品詳細頁）
    ↓
同時在背景執行 API 請求
    ↓
    ├─ 成功：console.log('✅ 已加入衣櫥')
    └─ 失敗：console.error('❌ 加入衣櫥失敗')
    ↓
用戶可以在衣櫥中看到新增的商品
```

## ✅ 優勢

1. **無縫體驗**：一鍵完成購買和保存
2. **自動化**：無需手動上傳圖片
3. **防重複**：自動檢查是否已存在
4. **來源追蹤**：標記為「品牌合作」和「Style Shop」
5. **GCS 整合**：圖片統一管理在 GCS

## 🔍 測試方式

### 前端測試

1. 進入「今日推薦」或「本日主打色」頁面
2. 找到店家商品（有藍色 Shop 徽章）
3. 點擊「購買」按鈕
4. 檢查：
   - 是否開啟新分頁（Style Shop）
   - Console 是否顯示「✅ 已加入衣櫥」
5. 進入「我的衣櫥」頁面
6. 確認商品已出現，標籤為「品牌合作」和「Style Shop」

### 後端測試

```bash
# 使用 curl 測試
curl -X POST \
  "https://cometical-kyphotic-deborah.ngrok-free.dev/api/v1/store/items/1/add-to-wardrobe" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📝 注意事項

1. **需要登入**：未登入用戶不會執行保存動作
2. **網路延遲**：保存動作在背景執行，不會阻塞跳轉
3. **錯誤處理**：保存失敗不影響跳轉功能
4. **GCS 權限**：確保後端有權限訪問兩個 GCS buckets

## 🚀 未來優化

1. **成功提示**：顯示 Toast 通知「已加入衣櫥」
2. **重複提示**：如果商品已存在，顯示「此商品已在衣櫥中」
3. **載入狀態**：按鈕顯示 loading 動畫
4. **批量加入**：支援一次加入多個商品
5. **願望清單**：先加入願望清單，稍後再購買

## 📚 相關文檔

- 後端 API 文檔：`app/api/v1/store.py`
- 店家商品服務：`app/services/store_items.py`
- 衣櫥模型：`app/models/wardrobe.py`
- GCS 服務：`app/services/storage.py`

---

**完成日期**：2025-12-03
**功能狀態**：✅ 已完成並測試
