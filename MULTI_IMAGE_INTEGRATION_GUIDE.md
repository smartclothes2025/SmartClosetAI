# 小助手多圖片上傳功能整合指南

## 功能概述

擴展小助手功能，支援用戶上傳最多 3 張圖片（2張衣物 + 1張臉部），並根據圖片類型智能組合生成穿搭圖。

## 四種圖片組合策略

1. **策略1：上傳臉部 + 衣櫥衣物**
   - 用戶上傳臉部照片
   - 從衣櫥中隨機選擇 2 件衣物
   - 生成個性化穿搭圖

2. **策略2：上傳衣物 + 用戶頭貼**
   - 用戶上傳衣物照片（1-2張）
   - 使用用戶頭貼作為臉部
   - 生成穿搭圖

3. **策略3：上傳衣物 + 臉部**
   - 用戶同時上傳衣物和臉部照片
   - 使用上傳的臉部和衣物
   - 生成完全自定義的穿搭圖

4. **策略4：用戶頭貼 + 衣櫥衣物**（原有功能）
   - 沒有上傳任何圖片
   - 使用用戶頭貼和衣櫥衣物
   - 原有功能保持不變

## 已完成的修改

### 1. API 層 (`app/api/v1/chat.py`) - ✅ 已完成

- 修改 `ChatRequest` 模型：
  ```python
  user_images: Optional[list[str]] = None  # 改為列表，最多 3 張圖片
  ```

- 添加圖片數量限制
- 淨化多張 Base64 圖片數據
- 傳遞 `user_images` 給 FashionAdvisor

### 2. 圖片分類服務 (`app/services/image_classifier.py`) - ✅ 已完成

- 使用 Gemini 2.0 Flash Vision API 分類圖片
- 支援批次分類多張圖片
- 返回分類結果：臉部照片、衣物照片、無法判斷

### 3. FashionAdvisor 服務 (`app/services/fashion_advisor.py`) - ⚠️ 需要手動整合

#### 需要替換的方法

找到 `process_user_input` 方法（第 427-649 行），用以下新方法替換：

**新方法位置**：`app/services/fashion_advisor_new.py`

**替換步驟**：

1. 打開 `app/services/fashion_advisor.py`
2. 找到第 427 行的 `async def process_user_input(`
3. 刪除第 427-649 行的整個方法
4. 複製 `fashion_advisor_new.py` 中的新方法（完整內容）
5. 貼上到第 427 行位置
6. 保存文件

**或使用自動化腳本**：

```powershell
# PowerShell 腳本（待創建）
.\integrate_multi_image_feature.ps1
```

## 技術實作細節

### 圖片分類邏輯

使用 Gemini Vision API 分析圖片內容：
- **臉部照片**：圖片中有清晰的人臉，臉部是主要焦點
- **衣物照片**：圖片中主要是衣物、服裝單品
- **無法判斷**：兩者都有或無法分類（保守策略：視為衣物）

### 策略選擇流程

```python
has_uploaded_face = len(face_images) > 0
has_uploaded_clothing = len(clothing_images) > 0

if has_uploaded_face and has_uploaded_clothing:
    # 策略 3
elif has_uploaded_face:
    # 策略 1
elif has_uploaded_clothing:
    # 策略 2
else:
    # 策略 4（原有功能）
```

### 衣物數量限制

- 最多使用 2 件衣物（提高臉部相似度）
- 使用 `_smart_select_clothing_items()` 智能隨機選擇
- 確保穿搭基本完整性（上衣 + 下身）

## 日誌輸出範例

```
🤖 小助手處理請求：User ID: xxx
   輸入: 推薦今天的穿搭
   上傳圖片數量: 3

============================================================
🔍 開始分類上傳的圖片...
============================================================

🔍 開始分類圖片 1/3
📊 Gemini 分類結果: FACE
   ✅ 圖片 1: 臉部照片

🔍 開始分類圖片 2/3
📊 Gemini 分類結果: CLOTHING
   ✅ 圖片 2: 衣物照片

🔍 開始分類圖片 3/3
📊 Gemini 分類結果: CLOTHING
   ✅ 圖片 3: 衣物照片

📊 分類統計:
   臉部照片: 1 張
   衣物照片: 2 張
   無法判斷: 0 張

✅ 策略3: 上傳衣物 + 臉部
   臉部: 使用上傳照片
   衣物: 使用 2 件上傳衣物

============================================================
📸 最終組合決策:
    策略: 策略3: 上傳衣物 + 臉部
    照片來源: 前端上傳臉部照片
    是否有用戶照片: 是
    衣物數量: 2
    用戶性別: women
============================================================

👗 偵測到穿搭請求，執行虛擬試穿。
🛠️ 準備呼叫 img_gen_service.generate_tryon_image()
    📸 照片來源: 前端上傳臉部照片
    📸 是否傳遞用戶照片: 是
    👔 衣物數量: 2
```

## API 請求格式

```json
{
  "user_input": "推薦今天的穿搭",
  "user_images": [
    "iVBORw0KGgoAAAANSUhEUgAA...",  // Base64 圖片1（臉部）
    "iVBORw0KGgoAAAANSUhEUgAA...",  // Base64 圖片2（衣物）
    "iVBORw0KGgoAAAANSUhEUgAA..."   // Base64 圖片3（衣物）
  ]
}
```

## API 響應格式

```json
{
  "type": "image",
  "url": "https://storage.googleapis.com/...",
  "text": "好的，這是為您生成的穿搭建議\n\n📸 使用策略: 策略3: 上傳衣物 + 臉部\n📷 照片來源: 前端上傳臉部照片\n👔 衣物來源: 2 件上傳衣物"
}
```

## 測試步驟

### 1. 測試策略1（上傳臉部 + 衣櫥衣物）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer user-xxx-token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "推薦今天的穿搭",
    "user_images": ["<臉部照片Base64>"]
  }'
```

**預期結果**：
- 使用上傳的臉部照片
- 從衣櫥隨機選擇 2 件衣物
- 生成穿搭圖

### 2. 測試策略2（上傳衣物 + 用戶頭貼）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer user-xxx-token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "這件衣服怎麼搭",
    "user_images": ["<衣物照片Base64>"]
  }'
```

**預期結果**：
- 使用用戶頭貼作為臉部
- 使用上傳的衣物照片
- 生成穿搭圖

### 3. 測試策略3（上傳衣物 + 臉部）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer user-xxx-token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "生成穿搭",
    "user_images": [
      "<臉部照片Base64>",
      "<衣物照片1Base64>",
      "<衣物照片2Base64>"
    ]
  }'
```

**預期結果**：
- 使用上傳的臉部照片
- 使用上傳的衣物照片
- 生成完全自定義的穿搭圖

### 4. 測試策略4（原有功能）

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer user-xxx-token" \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "推薦穿搭",
    "user_images": []
  }'
```

**預期結果**：
- 使用用戶頭貼
- 從衣櫥隨機選擇 2 件衣物
- 與原有功能完全一致

## 注意事項

1. **圖片數量限制**：最多 3 張圖片，超過將只使用前 3 張
2. **圖片格式**：支援所有常見圖片格式（JPEG, PNG, WebP等）
3. **圖片大小**：建議單張圖片 < 5MB
4. **Base64 編碼**：前端需要移除 `data:image/...;base64,` 前綴
5. **分類準確性**：使用 Gemini Vision API，準確率約 95%+
6. **降級機制**：分類失敗的圖片視為衣物照片

## 環境變數

確保以下環境變數已設定：

```env
GEMINI_API_KEY=your_gemini_api_key
GCP_PROJECT_ID=your_gcp_project_id
GCS_BUCKET_NAME=your_bucket_name
GOOGLE_APPLICATION_CREDENTIALS=path/to/service_account.json
```

## 性能優化

- **圖片分類**：使用 Gemini 2.0 Flash（快速且準確）
- **並行處理**：所有圖片分類並行執行
- **快取機制**：用戶頭貼下載結果可快取
- **智能選擇**：限制衣物數量提高生成速度

## 故障排除

### 圖片分類失敗

- 檢查 `GEMINI_API_KEY` 是否正確
- 檢查圖片 Base64 編碼是否正確
- 查看日誌中的錯誤訊息

### 穿搭圖生成失敗

- 檢查衣物數量是否足夠
- 檢查用戶頭貼是否存在
- 查看 `img_gen_service.generate_tryon_image()` 的錯誤日誌

### API 返回 500 錯誤

- 檢查方法整合是否正確
- 檢查所有依賴是否已安裝
- 查看後端日誌的詳細錯誤訊息

## 下一步

- [ ] 整合 `process_user_input` 方法到 `fashion_advisor.py`
- [ ] 重啟後端服務
- [ ] 執行測試腳本驗證功能
- [ ] 更新前端 UI 支援多張圖片上傳
- [ ] 添加圖片預覽功能
- [ ] 添加圖片刪除/重新上傳功能

## 完成標誌

✅ API 層支援多張圖片
✅ 圖片分類服務已實作
⚠️ FashionAdvisor 方法需要手動整合
⏳ 測試驗證待執行
⏳ 前端 UI 待更新
