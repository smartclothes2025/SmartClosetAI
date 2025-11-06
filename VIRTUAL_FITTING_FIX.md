# 虛擬試衣功能 - 問題修復總結

## ✅ 已完成的修復

### 1. 環境變數配置
- ✅ `GEMINI_API_KEY` 已修復（移除了錯誤的後綴）
- ✅ `GCP_PROJECT_ID` 已配置
- ✅ `GCP_LOCATION` 已配置  
- ✅ `GOOGLE_APPLICATION_CREDENTIALS` 路徑已配置
- ✅ `OPENAI_API_KEY` 已配置

### 2. 後端路由配置
- ✅ Virtual Fitting 路由已正確註冊在 `/api/v1/fitting/*`

## ⚠️ 需要前端修復的問題

### 404 Not Found 錯誤修復

**問題：** URL 路徑重複了 `/api/v1`
```
錯誤: POST /api/v1/api/v1/fitting/generate 
正確: POST /api/v1/fitting/generate
```

### 前端修復方案

#### 方案 1：檢查 API 基礎 URL

找到你的前端 API 配置檔案（通常在 `src/api/` 或 `src/services/`），檢查：

```javascript
// ❌ 錯誤示例
const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

// 在調用時
fetch(`${API_BASE_URL}/api/v1/fitting/generate`, ...)  
// 結果: /api/v1/api/v1/fitting/generate ❌

// ✅ 正確方式 1
const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';
fetch(`${API_BASE_URL}/fitting/generate`, ...)  
// 結果: /api/v1/fitting/generate ✅

// ✅ 正確方式 2
const API_BASE_URL = 'http://127.0.0.1:8000';
fetch(`${API_BASE_URL}/api/v1/fitting/generate`, ...)  
// 結果: /api/v1/fitting/generate ✅
```

#### 方案 2：如果使用 Axios

```javascript
// ❌ 錯誤配置
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/v1'
});

// 錯誤調用
api.post('/api/v1/fitting/generate', data);  
// 結果: /api/v1/api/v1/fitting/generate ❌

// ✅ 正確配置
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000/api/v1'
});

// 正確調用（注意沒有 /api/v1 前綴）
api.post('/fitting/generate', data);  
// 結果: /api/v1/fitting/generate ✅
```

#### 方案 3：使用環境變數

在 `.env.local` 或 `.env` 中：

```bash
# React
REACT_APP_API_URL=http://127.0.0.1:8000/api/v1

# Vue/Vite
VITE_API_URL=http://127.0.0.1:8000/api/v1

# Next.js
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
```

在代碼中：

```javascript
// React
const API_URL = process.env.REACT_APP_API_URL;

// Vue/Vite
const API_URL = import.meta.env.VITE_API_URL;

// Next.js
const API_URL = process.env.NEXT_PUBLIC_API_URL;

// 調用時
fetch(`${API_URL}/fitting/generate`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(data)
});
```

#### 方案 4：VirtualFitting.jsx 具體修復

找到你的 `VirtualFitting.jsx` 文件，修改 API 調用部分：

```jsx
// 在文件頂部
const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

// 在提交函數中
const handleGenerate = async () => {
  try {
    // ❌ 錯誤
    const response = await fetch(`${API_BASE_URL}/api/v1/fitting/generate`, {
      // ...
    });
    
    // ✅ 正確
    const response = await fetch(`${API_BASE_URL}/fitting/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_input: userInput,
        selected_items: selectedItems,
      })
    });
    
    const result = await response.json();
    // 處理結果...
  } catch (error) {
    console.error('生成失敗:', error);
  }
};
```

## 🧪 測試步驟

### 1. 重啟後端服務

```powershell
# 停止舊服務（如果正在運行）
# Ctrl+C

# 啟動新服務
.\start_backend.bat
# 或
python -m uvicorn app.main:app --reload
```

### 2. 運行診斷腳本

```powershell
python quick_fix_virtual_fitting.py
```

### 3. 測試 API

```powershell
python test_virtual_fitting_api.py
```

### 4. 手動測試（使用 curl）

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/fitting/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "user_input": "休閒穿搭",
    "selected_items": [
      {"id": 1, "name": "白T", "category": "上衣"}
    ]
  }'
```

或使用 curl（如果已安裝）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fitting/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "休閒穿搭",
    "selected_items": [
      {"id": 1, "name": "白T", "category": "上衣"}
    ]
  }'
```

## 📊 預期結果

### 配置正確時

```json
{
  "type": "text",
  "text": "⚠️ Imagen 圖片生成服務未配置...",
  "prompt_used": "Professional fashion photography..."
}
```

**說明：** 雖然無法生成圖片，但會返回詳細的文字描述和配置指南。

### 配置 Imagen 後

```json
{
  "type": "image",
  "url": "data:image/png;base64,iVBORw0KGgo...",
  "prompt_used": "Professional fashion photography..."
}
```

## 🔧 進階配置：啟用圖片生成

如果需要真正生成圖片，需要配置 Vertex AI Imagen：

### 1. 啟用 Vertex AI API

```bash
gcloud services enable aiplatform.googleapis.com
```

### 2. 確認服務帳號權限

服務帳號需要以下角色：
- `roles/aiplatform.user`
- `roles/storage.objectAdmin`（如果要上傳到 GCS）

### 3. 驗證配置

```python
# 測試腳本
python -c "import vertexai; vertexai.init(project='smartclothes-287af', location='us-central1'); print('✅ Vertex AI 配置成功')"
```

## 📝 常見問題

### Q: 為什麼還是返回 404？

A: 請檢查：
1. 前端 API URL 是否正確（不要重複 `/api/v1`）
2. 後端服務是否正在運行
3. 瀏覽器控制台中的實際請求 URL

### Q: 為什麼只返回文字而不是圖片？

A: 這是正常的！當前配置只有 Gemini API（文字），沒有 Imagen（圖片生成）。
要啟用圖片生成，需要：
1. 配置 Vertex AI
2. 啟用計費
3. 啟用 Imagen API

### Q: 如何查看詳細錯誤？

A: 查看後端終端輸出或日誌檔案：
- 終端直接顯示
- `logs/app.log`
- `logs/error.log`

## ✅ 檢查清單

- [ ] `.env` 檔案中 `GEMINI_API_KEY` 已配置
- [ ] 前端 API URL 路徑修復（移除重複的 `/api/v1`）
- [ ] 後端服務已重啟
- [ ] 運行 `quick_fix_virtual_fitting.py` 檢查配置
- [ ] 運行 `test_virtual_fitting_api.py` 測試 API
- [ ] 前端測試調用成功

## 📞 需要幫助？

如果問題仍未解決：
1. 運行診斷腳本並檢查輸出
2. 檢查後端日誌
3. 確認前端網絡請求的完整 URL
4. 提供詳細的錯誤訊息
