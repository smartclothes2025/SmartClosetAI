# 虛擬試衣功能配置與故障排除指南

## 問題診斷

### 錯誤：404 Not Found - `/api/v1/api/v1/fitting/generate`

**症狀：**
```
INFO: 127.0.0.1:52280 - "POST /api/v1/api/v1/fitting/generate HTTP/1.1" 404 Not Found
```

**原因：** 前端 API 調用時 URL 路徑重複了 `/api/v1`

**正確的 API 端點：**
- ✅ `/api/v1/fitting/generate`
- ❌ `/api/v1/api/v1/fitting/generate`（錯誤）

---

## 前端修復方案

### 方案 1：檢查 API 配置文件

如果你使用了 axios 或類似的 HTTP 客戶端，檢查 baseURL 配置：

```javascript
// ❌ 錯誤配置
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/v1'
});

// 調用時又加上了 /api/v1
api.post('/api/v1/fitting/generate', data);  // 結果: /api/v1/api/v1/fitting/generate

// ✅ 正確配置 - 方案 A
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/v1'
});
api.post('/fitting/generate', data);  // 結果: /api/v1/fitting/generate

// ✅ 正確配置 - 方案 B
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000'
});
api.post('/api/v1/fitting/generate', data);  // 結果: /api/v1/fitting/generate
```

### 方案 2：檢查環境變數

檢查 `.env` 或環境變數配置：

```bash
# 如果設置了這個
REACT_APP_API_BASE_URL=http://127.0.0.1:8000/api/v1

# 那麼調用時應該使用相對路徑
fetch(`${process.env.REACT_APP_API_BASE_URL}/fitting/generate`, ...)
```

### 方案 3：直接使用完整 URL

```javascript
// 最簡單的方式：使用完整 URL
fetch('http://127.0.0.1:8000/api/v1/fitting/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(data)
});
```

---

## AI 服務配置

虛擬試衣功能需要配置 Google AI 服務才能生成圖片。

### 選項 1：Google Gemini（推薦，有免費額度）

1. **獲取 API Key：**
   - 訪問：https://makersuite.google.com/app/apikey
   - 登入 Google 帳號
   - 點擊「Create API Key」
   - 複製生成的 API Key

2. **配置環境變數：**
   在 `.env` 文件中添加：
   ```bash
   GEMINI_API_KEY=your_api_key_here
   ```

3. **功能說明：**
   - ✅ 提供文字描述（免費）
   - ✅ 優化圖片生成提示詞（免費）
   - ❌ 不能直接生成圖片（需要 Imagen）

### 選項 2：Google Imagen（進階，需要付費）

1. **前置要求：**
   - Google Cloud Platform 帳號
   - 啟用計費
   - 啟用 Vertex AI API

2. **配置步驟：**

   a. 創建 GCP 項目：
   ```bash
   # 訪問 https://console.cloud.google.com/
   # 創建新項目或選擇現有項目
   ```

   b. 啟用 Vertex AI API：
   ```bash
   gcloud services enable aiplatform.googleapis.com
   ```

   c. 創建服務帳號並下載金鑰：
   ```bash
   gcloud iam service-accounts create smartcloset-ai \
     --display-name="SmartCloset AI Service Account"
   
   gcloud iam service-accounts keys create service-account-key.json \
     --iam-account=smartcloset-ai@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

   d. 授予權限：
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:smartcloset-ai@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```

3. **配置環境變數：**
   在 `.env` 文件中添加：
   ```bash
   GEMINI_API_KEY=your_gemini_api_key
   GCP_PROJECT_ID=your_project_id
   GCP_LOCATION=us-central1
   GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
   ```

4. **功能說明：**
   - ✅ 生成高質量圖片
   - ✅ 支持自定義尺寸
   - ✅ 專業時尚攝影風格
   - 💰 需要付費（按使用量計費）

---

## 測試 API

### 使用提供的測試腳本

```bash
python test_virtual_fitting_api.py
```

### 手動測試

使用 curl 測試：

```bash
# 測試正確的端點
curl -X POST http://127.0.0.1:8000/api/v1/fitting/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "休閒日常穿搭",
    "selected_items": [
      {
        "id": 1,
        "name": "白色T恤",
        "category": "上衣"
      }
    ]
  }'
```

### 預期響應

**未配置 AI 服務時：**
```json
{
  "type": "text",
  "text": "⚠️ AI 生成服務未配置\n\n請配置 GEMINI_API_KEY...",
  "url": null,
  "prompt_used": "..."
}
```

**配置 Gemini 但未配置 Imagen 時：**
```json
{
  "type": "text",
  "text": "⚠️ Imagen 圖片生成服務未配置\n\n當前使用 Gemini 生成文字描述...",
  "url": null,
  "prompt_used": "..."
}
```

**完整配置後：**
```json
{
  "type": "image",
  "url": "data:image/png;base64,iVBORw0KGgoAAAANS...",
  "text": null,
  "prompt_used": "Professional fashion photography..."
}
```

---

## 常見問題

### Q1: 為什麼返回 404 錯誤？

**A:** 檢查 URL 路徑是否正確：
- 正確：`/api/v1/fitting/generate`
- 錯誤：`/api/v1/api/v1/fitting/generate`

### Q2: 為什麼只返回文字描述而不是圖片？

**A:** 可能的原因：
1. 未配置 `GEMINI_API_KEY`
2. 未配置 `GCP_PROJECT_ID` 和 Imagen
3. GCP 服務帳號權限不足
4. Vertex AI API 未啟用

### Q3: 如何查看詳細的錯誤日誌？

**A:** 查看後端日誌輸出，已添加詳細的日誌記錄：
```
INFO: 收到虛擬試衣請求：2 件衣物
INFO: 開始生成圖片，使用提示詞長度：XXX 字元
INFO: 圖片生成結果：success=False
WARNING: 圖片生成失敗：請配置 GEMINI_API_KEY...
```

### Q4: 配置狀態如何檢查？

**A:** API 響應中會包含當前配置狀態：
```
**當前配置狀態：**
- GEMINI_API_KEY: ✅ 已配置 / ❌ 未配置
- GCP_PROJECT_ID: ✅ 已配置 / ❌ 未配置
```

---

## 後續步驟

1. ✅ 修復前端 API 調用路徑
2. ✅ 配置至少 GEMINI_API_KEY（獲得文字描述功能）
3. ⚪ 可選：配置 Imagen（獲得圖片生成功能）
4. ✅ 運行測試腳本驗證配置
5. ✅ 檢查後端日誌確認服務正常

---

## 技術支持

如遇到其他問題，請：
1. 檢查後端日誌輸出
2. 運行 `test_virtual_fitting_api.py` 測試腳本
3. 確認 `.env` 文件配置正確
4. 檢查 GCP 服務帳號權限
