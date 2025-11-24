# 用戶頭貼生成穿搭圖修復總結

## 🔍 問題診斷

從日誌發現以下問題：

1. **用戶照片確實下載成功了**：
   ```
   ✅ 成功下載並使用用戶頭貼！
   Base64 長度: 13652 chars
   ```

2. **但 content_parts 數量錯誤**：
   ```
   內容部分數量: 15 (應該是 16)
   實際: 1 prompt + 14 clothing_images = 15
   預期: 1 prompt + 1 user_photo + 14 clothing_images = 16
   ```

3. **圖片編號不匹配**：
   - 提示詞說：「Image #1 是用戶照片，Images #2 onwards 是衣物」
   - 但 clothing_description 說：「第1張圖片、第2張圖片...」（從1開始）
   - Gemini 不知道哪張是用戶照片

## ✅ 修復方案

### 1. 增強用戶照片添加日誌

**位置**：`image_generation.py` 第 361-400 行

**修改**：
- ✅ 添加 `user_photo_added` 標誌變量
- ✅ 記錄 Base64 長度
- ✅ 記錄解碼後圖片大小
- ✅ 驗證圖片格式
- ✅ 根據實際格式動態設置 `mime_type`
- ✅ 記錄用戶照片在 content_parts 中的 Index
- ✅ 完整的異常追蹤（`exc_info=True`）

**新增日誌**：
```
📸 檢測到用戶照片，正在處理...
   Base64 長度: 13652 chars
   解碼後圖片大小: 4841 bytes (4.7 KB)
   用戶照片驗證通過 - 格式: JPEG, 尺寸: 259x194, 模式: RGB
✅ 用戶照片已成功添加到 content_parts (Index: 1)
   Mime Type: image/jpeg
   Data Size: 4.7 KB
📊 當前 content_parts 數量: 2 (應該是: 1 prompt+ 1 user_photo)
```

### 2. 修復圖片編號不匹配

**位置**：`image_generation.py` 第 219-233 行

**修改**：
- ✅ 當有用戶照片時，衣物從 **Image #2** 開始編號
- ✅ 無用戶照片時，衣物從 **第1張圖片** 開始

**修改前**：
```python
item_index = 1
for ...:
    clothing_details.append(f"第{item_index}張圖片: ...")
```

**修改後**：
```python
item_index = 2 if user_photo_base64 else 1
for ...:
    if user_photo_base64:
        clothing_details.append(f"Image #{item_index}: ...")
    else:
        clothing_details.append(f"第{item_index}張圖片: ...")
```

### 3. 自動修正提示詞不匹配

**位置**：`image_generation.py` 第 402-476 行

**問題**：如果用戶照片添加失敗，但已經生成了「有用戶照片」的提示詞

**解決方案**：
- 檢測 `user_photo_base64 and not user_photo_added` 的情況
- 自動重新生成「預設模特兒」提示詞
- 更新 clothing_description（從 Image #1 開始）
- 替換 content_parts[0] 的提示詞

### 4. 增強最終驗證日誌

**位置**：`image_generation.py` 第 498-517 行

**新增日誌**：
```
🚀 開始調用 Gemini 2.5 Flash Image 模型...
   實際 content_parts 數量: 16
   預期數量: 16 (1 prompt + 1 user_photo + 14 clothing_images)
   ✅ 數量匹配！
   📸 用戶照片: Image #1
   👔 衣物圖片: Image #2 to #15
```

## 📊 預期日誌輸出

### 成功場景（有用戶照片）

```
INFO: 📸 優先級 2: 沒有上傳照片，準備下載用戶頭貼
INFO:     原始 URI: 'gs://smartclothes_userphoto/8823573a-6d4f-441b-b15b-95f90781fb23/王世堅.jpg'
INFO: 🔄 開始下載用戶頭貼...
INFO: ✅ 成功下載並使用用戶頭貼！
INFO:     Base64 長度: 13652 chars

INFO: 📸 檢測到用戶照片，正在處理...
INFO:    Base64 長度: 13652 chars
INFO:    解碼後圖片大小: 4841 bytes (4.7 KB)
INFO:    用戶照片驗證通過 - 格式: JPEG, 尺寸: 259x194, 模式: RGB
INFO: ✅ 用戶照片已成功添加到 content_parts (Index: 1)
INFO:    Mime Type: image/jpeg
INFO:    Data Size: 4.7 KB
INFO: 📊 當前 content_parts 數量: 2 (應該是: 1 prompt+ 1 user_photo)

INFO: [載入 14 件衣物...]

INFO: 🚀 開始調用 Gemini 2.5 Flash Image 模型...
INFO:    實際 content_parts 數量: 16
INFO:    預期數量: 16 (1 prompt + 1 user_photo + 14 clothing_images)
INFO:    ✅ 數量匹配！
INFO:    📸 用戶照片: Image #1
INFO:    👔 衣物圖片: Image #2 to #15
```

### 失敗場景（用戶照片添加失敗）

```
INFO: 📸 檢測到用戶照片，正在處理...
ERROR: ❌ 用戶照片處理失敗: [錯誤訊息]
ERROR:    將使用預設模特兒生成
INFO: 📊 當前 content_parts 數量: 1 (應該是: 1 prompt)

WARNING: ⚠️ 用戶照片未成功添加，但使用了有用戶照片的提示詞！
WARNING:    將重新生成預設模特兒提示詞...
INFO: ✅ 已重新生成預設模特兒提示詞

INFO: 🚀 開始調用 Gemini 2.5 Flash Image 模型...
INFO:    實際 content_parts 數量: 15
INFO:    預期數量: 15 (1 prompt + 14 clothing_images)
INFO:    ✅ 數量匹配！
INFO:    👔 衣物圖片: Image #1 to #14
```

## 🧪 測試步驟

1. **重啟後端服務**：
   ```powershell
   # 停止現有服務
   # 重新啟動
   python -m uvicorn app.main:app --reload
   ```

2. **發送測試請求**：
   - 在小助手輸入「穿搭」或「今天穿什麼」
   - 確保用戶有頭貼：`gs://smartclothes_userphoto/{user_id}/王世堅.jpg`

3. **檢查日誌**：
   - 尋找 `📸 檢測到用戶照片，正在處理...`
   - 檢查 `✅ 用戶照片已成功添加到 content_parts`
   - 確認 `實際 content_parts 數量: 16` 和 `✅ 數量匹配！`

4. **驗證結果**：
   - 生成的穿搭圖應該使用用戶的臉
   - 檢查返回的照片來源：`📸 照片來源: 用戶頭貼`

## 🔧 故障排除

### 如果 content_parts 數量仍然不匹配

**可能原因**：
1. 用戶照片添加時拋出異常（檢查異常日誌）
2. Base64 解碼失敗
3. 圖片格式驗證失敗

**檢查點**：
- 日誌中是否有 `❌ 用戶照片處理失敗`
- 異常的詳細追蹤訊息（`exc_info=True`）

### 如果 Gemini 仍然生成預設模特兒

**可能原因**：
1. 提示詞和圖片順序不匹配
2. 用戶照片質量太低
3. Gemini 沒有正確識別 Image #1

**檢查點**：
- 確認 `📸 用戶照片: Image #1`
- 確認 `👔 衣物圖片: Image #2 to #15`
- 檢查用戶照片是否清晰、正面、有臉部

## 📝 關鍵變更總結

| 文件 | 行數 | 變更內容 |
|------|------|----------|
| `image_generation.py` | 219-233 | 修復圖片編號（有用戶照片時從 #2 開始） |
| `image_generation.py` | 361-400 | 增強用戶照片添加日誌和錯誤處理 |
| `image_generation.py` | 402-476 | 自動修正提示詞不匹配 |
| `image_generation.py` | 498-517 | 增強最終驗證日誌 |

## ✨ 預期改善

1. **更清楚的日誌**：
   - 可以看到用戶照片是否成功添加
   - 可以看到 content_parts 數量是否正確
   - 可以看到圖片編號是否匹配

2. **自動修正**：
   - 如果用戶照片添加失敗，自動切換到預設模特兒提示詞
   - 確保提示詞和實際圖片順序一致

3. **正確的圖片順序**：
   - Image #1: 用戶照片
   - Image #2~#15: 14 件衣物
   - Gemini 應該能正確識別並使用用戶的臉

---

**測試完成後請查看日誌並回報結果！**
