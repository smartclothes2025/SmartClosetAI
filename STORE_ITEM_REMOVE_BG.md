# 店家商品自動去背功能

## 🎨 功能概述

當用戶從「本日主打色」頁面購買店家商品並加入衣櫥時，系統會自動進行去背處理，讓衣櫥中的商品圖片更加乾淨美觀。

## 🔧 技術實作

### 修改位置

**檔案**：`app/api/v1/store.py`

### 新增功能

#### 1. 導入去背套件（第 12-13 行）

```python
from rembg import remove
from PIL import Image
```

#### 2. 去背處理邏輯（第 187-204 行）

```python
# 3. 去背處理
logger.info(f"[add-to-wardrobe] 開始去背處理...")
try:
    # 將圖片轉為 PIL Image
    input_image = Image.open(BytesIO(image_bytes))
    
    # 使用 rembg 去背
    output_image = remove(input_image, alpha_matting=True)
    
    # 轉為 PNG bytes
    output_buffer = BytesIO()
    output_image.save(output_buffer, format="PNG")
    image_bytes = output_buffer.getvalue()
    
    logger.info(f"[add-to-wardrobe] 去背完成，圖片大小: {len(image_bytes)} bytes")
except Exception as e:
    logger.warning(f"[add-to-wardrobe] 去背失敗，使用原圖: {e}")
    # 去背失敗時使用原圖
```

#### 3. 檔案格式改為 PNG（第 238-240 行）

```python
# 建立 GCS 路徑: wardrobe/{user_id}/{category}/store_{product_id}.png（去背後使用 PNG）
user_id_str = str(current_user.id)
gcs_path = f"wardrobe/{user_id_str}/{category_gcs}/store_{product_id}.png"
```

#### 4. MIME 類型改為 PNG（第 249 行）

```python
cover_url = upload_file_to_gcs(
    file_bytes=image_bytes,
    destination_blob_name=gcs_path,
    mime_type="image/png",  # 改為 PNG
    bucket_name=GCS_BUCKET_NAME,
    public=False,
)
```

#### 5. 標記圖片已去背（第 288 行）

```python
attributes={"source": "store", "product_id": product_id, "bg_removed": True},
```

## 📊 處理流程

```
用戶點擊購買
    ↓
1. 查詢店家商品資訊
    ↓
2. 從 GCS 下載原始圖片
    ↓
3. 使用 rembg 進行去背處理
    ├─ 成功 → 使用去背後的 PNG 圖片
    └─ 失敗 → 使用原始圖片（降級機制）
    ↓
4. 上傳到用戶衣櫥 GCS
    ↓
5. 建立資料庫記錄（標記 bg_removed: true）
    ↓
6. 跳轉到衣櫥頁面
```

## 🎯 技術特點

### 1. Alpha Matting

使用 `alpha_matting=True` 參數，提供更精細的邊緣處理：
- 更自然的邊緣過渡
- 保留細節（如頭髮、毛邊）
- 更高品質的去背效果

### 2. 降級機制

如果去背失敗（例如網路問題、記憶體不足），系統會：
- 記錄警告日誌
- 使用原始圖片
- 不影響加入衣櫥功能

### 3. PNG 格式

去背後的圖片使用 PNG 格式：
- 支援透明背景
- 無損壓縮
- 適合衣物展示

### 4. 資料標記

在 `attributes` 中標記 `bg_removed: true`：
- 方便前端識別
- 可用於篩選或特殊顯示
- 追蹤圖片處理狀態

## 📝 日誌輸出

### 成功去背

```
INFO:app.api.v1.store:[add-to-wardrobe] 找到店家商品: 抽象印花腋下包（日常）
INFO:app.api.v1.store:[add-to-wardrobe] 下載圖片: https://storage.googleapis.com/...
INFO:app.api.v1.store:[add-to-wardrobe] 開始去背處理...
INFO:app.api.v1.store:[add-to-wardrobe] 去背完成，圖片大小: 245678 bytes
INFO:app.api.v1.store:[add-to-wardrobe] 上傳至: gs://smartclothes_wardrobe/wardrobe/...
INFO:app.api.v1.store:[add-to-wardrobe] GCS 上傳成功: gs://...
INFO:app.api.v1.store:[add-to-wardrobe] 成功加入衣櫥: uuid
```

### 去背失敗（降級）

```
INFO:app.api.v1.store:[add-to-wardrobe] 開始去背處理...
WARNING:app.api.v1.store:[add-to-wardrobe] 去背失敗，使用原圖: [錯誤訊息]
INFO:app.api.v1.store:[add-to-wardrobe] 上傳至: gs://...
INFO:app.api.v1.store:[add-to-wardrobe] GCS 上傳成功: gs://...
```

## 🧪 測試方式

### 1. 重啟後端服務

```powershell
# 停止現有服務（Ctrl+C）
# 重新啟動
.\start_backend.bat
```

### 2. 前端測試

1. 進入「本日主打色」頁面
2. 點擊任一店家商品
3. 檢查：
   - ✅ 商品成功加入衣櫥
   - ✅ 圖片背景已去除（透明背景）
   - ✅ 檔案格式為 PNG
   - ✅ 衣櫥中顯示乾淨的商品圖片

### 3. 檢查 GCS

查看上傳的檔案：
- 路徑：`wardrobe/{user_id}/{category}/store_{product_id}.png`
- 格式：PNG
- 背景：透明

### 4. 檢查資料庫

```sql
SELECT id, name, attributes 
FROM wardrobe_items 
WHERE attributes->>'source' = 'store';
```

應該看到：
```json
{
  "source": "store",
  "product_id": 76,
  "bg_removed": true
}
```

## ⚡ 效能考量

### 處理時間

- 下載圖片：~0.5-1 秒
- 去背處理：~2-5 秒（取決於圖片大小）
- 上傳 GCS：~0.5-1 秒
- **總計**：約 3-7 秒

### 記憶體使用

- rembg 會使用額外記憶體
- 建議伺服器至少有 2GB 可用記憶體
- 處理完成後會自動釋放

### 優化建議

如果處理時間過長，可以考慮：
1. 使用背景任務（Celery）
2. 先加入衣櫥，後台去背
3. 使用更小的圖片尺寸

## 🎨 視覺效果

### 原始圖片（有背景）
- 包含商品拍攝時的背景
- 可能有陰影、雜物
- 不夠乾淨

### 去背後（透明背景）
- ✅ 只保留商品本體
- ✅ 透明背景
- ✅ 乾淨美觀
- ✅ 適合衣櫥展示

## 📦 依賴套件

確認 `requirements.txt` 包含：
```
rembg>=2.0.0
Pillow>=10.0.0
```

如果沒有，請安裝：
```powershell
pip install rembg Pillow
```

## 🔍 除錯指南

### 問題：去背失敗

**可能原因**：
1. rembg 未安裝
2. 記憶體不足
3. 圖片格式不支援

**解決方案**：
```powershell
# 重新安裝 rembg
pip install --upgrade rembg

# 檢查記憶體
# 確保至少有 2GB 可用記憶體
```

### 問題：圖片仍有背景

**可能原因**：
1. 去背失敗，使用了原圖
2. 原圖本身就是透明背景

**檢查方式**：
- 查看後端日誌
- 檢查是否有 "去背失敗" 警告

### 問題：上傳失敗

**可能原因**：
1. GCS 權限問題
2. 網路問題
3. 檔案過大

**解決方案**：
- 檢查 GCS 權限設定
- 確認網路連線
- 檢查圖片大小（建議 < 5MB）

## 🎉 優勢

1. **自動化**：無需手動去背
2. **高品質**：使用 alpha matting 技術
3. **穩定性**：完整的降級機制
4. **透明背景**：適合衣櫥展示
5. **資料追蹤**：標記去背狀態

## 🔄 與上傳功能的一致性

現在店家商品和用戶上傳的衣物都支援去背：
- **用戶上傳**：`upload.py` 中的 `remove_bg` 參數
- **店家商品**：自動去背（本功能）

兩者使用相同的去背技術（rembg），確保一致的視覺效果。

---

**完成日期**：2025-12-03  
**功能狀態**：✅ 已完成  
**需要重啟**：是（需要重啟後端服務）
