# 虛擬試衣 GCS 圖片載入修復

## 問題描述

虛擬試衣功能無法載入儲存在 Google Cloud Storage (GCS) 的衣物圖片，導致生成失敗。

### 錯誤日誌
```
WARNING:app.services.image_generation:   ⚠️ 跳過: 無圖片 URL
WARNING:app.services.image_generation:   ⚠️ 跳過: 無圖片 URL
ERROR:app.services.image_generation:❌ 沒有成功載入任何衣物圖片,無法進行虛擬試穿
```

## 根本原因

1. **前端傳送的圖片 URL 為空**
   - 前端從 `/api/v1/clothes` 獲取衣物清單時，後端會將 GCS URI 轉換為簽署 URL
   - 簽署 URL 有效期為 60 分鐘
   - 當使用者在選擇衣物後過了一段時間才執行虛擬試衣，簽署 URL 可能已過期
   - 或者前端在傳送時沒有正確包含 `img` 欄位

2. **資料流程問題**
   ```
   資料庫 (GCS URI: gs://bucket/path)
     ↓
   GET /api/v1/clothes (轉換為簽署 URL)
     ↓
   前端 localStorage (儲存簽署 URL)
     ↓
   POST /api/v1/fitting/generate (簽署 URL 可能已過期)
     ↓
   ❌ 無法載入圖片
   ```

## 解決方案

### 修改虛擬試衣 API，從資料庫重新獲取 GCS URI

修改 `app/api/v1/virtual_fitting.py`，讓 API 在收到請求時：
1. 根據前端傳來的衣物 ID，從資料庫重新查詢衣物資料
2. 直接使用資料庫中的原始 GCS URI（`gs://...`）
3. 圖片生成服務會直接從 GCS 下載圖片，不需要簽署 URL

### 關鍵改動

```python
@router.post("/generate", response_model=VirtualFittingResponse)
async def generate_virtual_fitting(request: VirtualFittingRequest, db: Session = Depends(get_db)):
    # ✅ 從資料庫重新獲取衣物資料
    from app.models.wardrobe import WardrobeItem
    items_dict = []
    
    for item in request.selected_items:
        # 從資料庫查詢衣物
        db_item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()
        
        if db_item:
            items_dict.append({
                'id': str(db_item.id),
                'name': db_item.name,
                'category': db_item.category.value,
                'img': db_item.cover_image_url  # ✅ 直接使用 GCS URI
            })
```

### 優點

1. **不依賴前端傳來的圖片 URL**
   - 即使前端的簽署 URL 過期，也能正常工作
   - 前端可以傳送 `img: null`，API 會自動從資料庫獲取

2. **直接使用 GCS URI**
   - 圖片生成服務已支援從 GCS 下載（`_download_image` 方法）
   - 不需要簽署 URL，直接使用服務帳號權限下載

3. **更可靠的資料來源**
   - 資料庫是單一真實來源（Single Source of Truth）
   - 避免前端資料過時或不完整的問題

## 測試方法

### 1. 使用測試腳本

```bash
python test_virtual_fitting_with_db.py
```

這個腳本會：
- 從資料庫獲取有 GCS 圖片的衣物
- 故意將 `img` 欄位設為 `null`
- 呼叫虛擬試衣 API
- 驗證 API 是否能從資料庫重新獲取圖片 URL

### 2. 檢查後端日誌

成功的日誌應該顯示：
```
INFO:app.api.v1.virtual_fitting:從資料庫載入衣物 ID=123, 圖片 URL=gs://bucket/path/to/image.jpg
INFO:app.services.image_generation:📥 [1/2] 下載: 白色T恤 (上衣)
INFO:app.services.image_generation:   URL: gs://bucket/path/to/image.jpg
INFO:app.services.image_generation:   從 GCS 下載: bucket=bucket, blob=path/to/image.jpg
INFO:app.services.image_generation:   GCS 下載成功: 123456 bytes
INFO:app.services.image_generation:   ✅ 成功載入 (大小: 120.5 KB)
```

### 3. 前端測試

前端不需要修改，但可以驗證：
1. 選擇衣物進行虛擬試衣
2. 即使等待一段時間（超過 60 分鐘），虛擬試衣仍能正常工作
3. 檢查瀏覽器開發者工具，確認請求成功

## 前置條件

### 1. GCS 認證配置

確保環境變數已設定：
```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
GCS_BUCKET_NAME=your-bucket-name
```

### 2. 服務帳號權限

GCS 服務帳號需要有以下權限：
- `storage.objects.get` - 讀取物件
- `storage.objects.list` - 列出物件

### 3. 資料庫中的圖片 URL 格式

確保 `wardrobe_items.cover_image_url` 欄位儲存的是 GCS URI：
```
gs://bucket-name/wardrobe/user-id/category/filename.jpg
```

而不是簽署 URL：
```
https://storage.googleapis.com/bucket-name/...?X-Goog-Signature=...
```

## 驗證清單

- [ ] 後端服務正在運行
- [ ] GCS 認證已正確配置
- [ ] 資料庫中有衣物記錄，且 `cover_image_url` 是 GCS URI
- [ ] 執行測試腳本，確認能成功載入圖片
- [ ] 檢查後端日誌，確認從 GCS 下載成功
- [ ] 前端測試虛擬試衣功能

## 相關檔案

- `app/api/v1/virtual_fitting.py` - 虛擬試衣 API（已修改）
- `app/services/image_generation.py` - 圖片生成服務（支援 GCS 下載）
- `app/api/v1/clothes.py` - 衣物 API（產生簽署 URL 供前端顯示）
- `test_virtual_fitting_with_db.py` - 測試腳本

## 注意事項

1. **前端顯示仍使用簽署 URL**
   - 衣物清單 API (`/api/v1/clothes`) 仍會產生簽署 URL
   - 這是為了讓前端能直接顯示圖片（瀏覽器無法直接訪問 GCS URI）
   - 虛擬試衣 API 則直接使用 GCS URI，由後端下載

2. **效能考量**
   - 從資料庫查詢衣物會增加少量延遲（通常 < 10ms）
   - 但相比圖片生成時間（10-30 秒），這個延遲可以忽略

3. **錯誤處理**
   - 如果資料庫中找不到衣物，會使用前端傳來的資料（向下相容）
   - 如果 GCS 下載失敗，會記錄詳細錯誤日誌

## 最新更新：亞洲（台灣）女性模特兒

### 修改內容
在圖片生成提示詞中加入了明確的模特兒要求：
- ✅ **必須是亞洲女性（台灣）**
- 東亞面孔特徵，自然黑髮或深棕色頭髮
- 膚色：自然的亞洲膚色（偏白皙到自然膚色）
- 身材：符合亞洲女性平均身材比例
- 年齡：20-30 歲左右的年輕女性

### 修改位置
1. `_generate_with_clothing_images` 方法中的 `tryon_prompt`（使用實際衣物圖片時）
2. `create_fashion_prompt` 方法（純文字描述生成時）

### 效果
生成的虛擬試衣圖片將使用亞洲（台灣）女性模特兒，更符合目標用戶的需求。

## 後續改進建議

1. **快取機制**
   - 可以快取下載的圖片，避免重複下載
   - 但需要考慮快取失效策略

2. **批次查詢優化**
   - 目前是逐一查詢衣物，可以改為批次查詢
   - 使用 `WHERE id IN (...)` 一次查詢所有衣物

3. **前端改進**
   - 前端可以只傳送衣物 ID，不傳送其他欄位
   - API 完全從資料庫獲取資料，簡化前端邏輯

4. **模特兒多樣性**
   - 可以讓使用者選擇不同的模特兒類型
   - 支援不同身材、膚色、年齡的選項
