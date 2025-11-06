# 虛擬試穿改進測試指南

## 🚀 快速測試步驟

### 1. 啟動後端服務

```powershell
# 方法 1: 使用啟動腳本
.\start_backend.bat

# 方法 2: 使用 PowerShell 腳本
.\start.ps1

# 方法 3: 直接運行
python start_server.py
```

### 2. 監控後端日誌

**在另一個終端視窗中**運行：

```powershell
.\watch_backend_output.ps1
```

這會實時顯示後端日誌，包括：
- 🎯 虛擬試穿開始標記
- 📥 衣物圖片下載進度
- ✅ 成功/失敗狀態
- 🎉 生成結果

### 3. 運行自動化測試

```powershell
python test_virtual_fitting_improvements.py
```

這會執行 4 個測試場景：
1. ✅ 使用實際衣物圖片生成
2. ✅ 純文字生成 fallback
3. ✅ 處理無效圖片 URL
4. ✅ 類別映射測試

### 4. 前端手動測試

1. 打開前端應用
2. 進入「虛擬試衣」頁面
3. 選擇 2-3 件衣物（建議：上衣 + 裙子）
4. 點擊「生成試穿效果」
5. 觀察結果

## 🔍 檢查清單

### 後端日誌檢查

在 `watch_backend_output.ps1` 視窗中查看：

```
✅ 應該看到:
============================================================
🎯 開始虛擬試穿圖片生成
衣物數量: 2
分類統計: [('tops', 1), ('bottoms', 1)]
============================================================

📥 [1/2] 下載: 白色襯衫 (上衣)
   URL: https://storage.googleapis.com/...
   ✅ 成功載入 (大小: 156.3 KB)

📥 [2/2] 下載: 黑色裙子 (裙子)
   ✅ 成功載入 (大小: 89.7 KB)

============================================================
📊 圖片載入統計:
   成功: 2/2
============================================================

🚀 開始調用 Gemini 2.5 Flash Image 模型...
   內容部分數量: 3 (1 prompt + 2 images)

============================================================
🎉 虛擬試穿圖片生成成功!
   圖片大小: 245.8 KB
   使用衣物圖片: 2 張
   生成服務: Gemini 2.5 Flash Image (多模態)
============================================================
```

### 前端顯示檢查

生成成功後，應該看到：

```
✅ 使用 2 張實際衣物圖片生成
```

**如果看到以下訊息，表示使用了 fallback：**

```
⚠️ 僅使用文字描述生成 (未使用實際衣物圖片)
```

### 生成結果檢查

檢查生成的圖片是否：
- [ ] 包含所有選中的衣物
- [ ] 衣物顏色與原圖相符
- [ ] 衣物沒有被錯誤合併（如上衣+裙子→連衣裙）
- [ ] 模特兒姿態自然
- [ ] 背景簡潔專業

## 🐛 常見問題排查

### 問題 1: 圖片下載失敗

**症狀：**
```
❌ 下載失敗: HTTP 403
```

**原因：** GCS 圖片 URL 權限問題或 CORS 配置

**解決方案：**
```powershell
# 檢查 GCS 配置
python check_gcs.py

# 更新 CORS 配置
gsutil cors set cors-config.json gs://smartcloset-ai.appspot.com
```

### 問題 2: 使用了 fallback 而非實際圖片

**症狀：**
```
🔄 Fallback: 使用純文字生成模式
```

**原因：** 所有衣物圖片下載失敗

**解決方案：**
1. 檢查網路連接
2. 驗證圖片 URL 是否可訪問
3. 檢查 GCS 權限設置

### 問題 3: 生成的衣物不符

**症狀：** 生成的圖片中衣物與選擇的不同

**可能原因：**
1. **使用了 text_only_fallback** - 檢查日誌確認
2. **AI 模型限制** - 模型理解錯誤（即使使用了實際圖片）

**解決方案：**
- 如果是原因 1：修復圖片下載問題
- 如果是原因 2：這是 AI 模型的固有限制，可以：
  - 多次生成，選擇最佳結果
  - 調整用戶輸入提示詞
  - 考慮使用專業虛擬試穿模型

### 問題 4: API 錯誤

**症狀：**
```
❌ 虛擬試穿圖片生成錯誤
   錯誤類型: ResourceExhausted
```

**原因：** Gemini API 配額用盡或限流

**解決方案：**
1. 等待幾分鐘後重試
2. 檢查 Google Cloud Console 中的 API 配額
3. 考慮升級 API 計劃

## 📊 測試場景

### 場景 1: 單件衣物

**選擇：** 1 件上衣

**預期結果：**
- 生成穿著該上衣的模特兒照片
- 下半身為通用褲子或裙子

### 場景 2: 上下搭配

**選擇：** 1 件上衣 + 1 件裙子/褲子

**預期結果：**
- 生成穿著兩件衣物的模特兒照片
- **關鍵檢查：** 不應該合併成連衣裙

### 場景 3: 完整穿搭

**選擇：** 上衣 + 褲子 + 外套 + 鞋子

**預期結果：**
- 生成完整穿搭效果圖
- 所有衣物都應該出現

### 場景 4: 洋裝

**選擇：** 1 件洋裝

**預期結果：**
- 生成穿著洋裝的模特兒照片
- 不應該添加額外的上衣或褲子

## 📈 性能指標

### 正常指標

- **圖片下載時間：** 每張 < 3 秒
- **AI 生成時間：** 10-30 秒
- **總處理時間：** < 40 秒
- **圖片大小：** 100-500 KB (base64)

### 異常指標

- ⚠️ 圖片下載時間 > 5 秒 - 網路問題
- ⚠️ AI 生成時間 > 60 秒 - API 問題
- ⚠️ 總處理時間 > 90 秒 - 需要優化

## 🔧 調試技巧

### 1. 啟用詳細日誌

在 `.env` 文件中添加：

```env
LOG_LEVEL=DEBUG
```

### 2. 檢查特定衣物圖片

```python
import requests
from PIL import Image
from io import BytesIO

# 測試圖片 URL
url = "https://storage.googleapis.com/smartcloset-ai.appspot.com/uploads/tops/top_1.jpg"

response = requests.get(url)
print(f"Status: {response.status_code}")
print(f"Size: {len(response.content)} bytes")

if response.status_code == 200:
    img = Image.open(BytesIO(response.content))
    print(f"Image size: {img.size}")
    print(f"Image mode: {img.mode}")
```

### 3. 直接測試 Gemini API

```python
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash-image')

response = model.generate_content("A fashion model wearing a white shirt")
print(f"Response parts: {len(response.parts)}")
```

## 📝 報告問題

如果遇到問題，請提供：

1. **後端日誌** - 完整的日誌輸出
2. **選擇的衣物** - 衣物名稱和類別
3. **生成結果** - 成功/失敗，使用的方法
4. **錯誤訊息** - 完整的錯誤堆疊
5. **環境信息** - Python 版本，API Key 狀態

## 🎯 成功標準

測試被認為成功，當：

- ✅ 後端日誌顯示「🎉 虛擬試穿圖片生成成功!」
- ✅ 使用了「multimodal_with_actual_clothing_images」方法
- ✅ 所有衣物圖片成功下載
- ✅ 生成的圖片包含選中的衣物
- ✅ 前端顯示「✅ 使用 X 張實際衣物圖片生成」

---

**相關文檔：**
- [虛擬試穿改進文檔](docs/backend/VIRTUAL_FITTING_IMPROVEMENTS.md)
- [虛擬試穿設置指南](docs/VIRTUAL_FITTING_SETUP.md)
