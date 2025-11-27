# 多圖片上傳功能修復

## 問題診斷

**症狀：**
用戶上傳衣物圖片後，後端沒有收到圖片數據，導致使用了預設策略（用戶頭貼 + 衣櫥衣物）而不是上傳的衣物。

**日誌證據：**
```
INFO:app.api.v1.chat:收到 / 請求, Payload: user_input='穿搭' user_images=None
INFO:app.services.fashion_advisor:   上傳圖片數量: 0
```

## 根本原因

前端發送的 API 參數名稱與後端不匹配：

| 組件 | 參數名 | 狀態 |
|------|--------|------|
| 前端（舊） | `images` | ❌ 錯誤 |
| 前端（舊） | `image_names` | ❌ 不需要 |
| 後端 | `user_images` | ✅ 正確 |

## 修復內容

### 1. 前端 API 請求修復

**文件：** `frontend/src/pages/Assistant.jsx`

**修改位置：** 第 315-329 行

**修改內容：**
```javascript
// ❌ 舊代碼（錯誤）
const payload = {
  user_input: txt,
  images: imagesToSend.map((img) => img.dataUrl),      // 錯誤的參數名
  image_names: imagesToSend.map((img) => img.name),    // 不需要
};

// ✅ 新代碼（正確）
const imagesToSendLimited = imagesToSend.slice(0, 3);  // 限制最多 3 張
const payload = {
  user_input: txt || "穿搭",                            // 如果只有圖片，使用預設文字
  user_images: imagesToSendLimited.map((img) => img.dataUrl), // 正確的參數名
};
```

### 2. 圖片數量限制

**前端限制（2 處）：**

1. **上傳時限制：** `handleFileChange()` 函數（第 392-397 行）
   ```javascript
   const maxImages = 3;
   const filesToProcess = files.slice(0, maxImages);
   if (files.length > maxImages) {
     addMessage("assistant", `⚠️ 最多只能上傳 ${maxImages} 張圖片`);
   }
   ```

2. **發送時限制：** `handleSend()` 函數（第 315-319 行）
   ```javascript
   const imagesToSendLimited = imagesToSend.slice(0, 3);
   if (imagesToSend.length > 3) {
     console.warn(`⚠️ 收到 ${imagesToSend.length} 張圖片，超過限制`);
   }
   ```

**後端限制：** `app/api/v1/chat.py`（第 102-105 行）
```python
if len(user_images) > 3:
    logger.warning(f"⚠️ 收到 {len(user_images)} 張圖片，超過限制（最多 3 張）")
    user_images = user_images[:3]
```

### 3. 調試日誌

新增了前端和後端的調試日誌：

**前端：**
```javascript
console.log('📤 發送請求:', {
  user_input: payload.user_input,
  image_count: payload.user_images?.length || 0
});

console.log('📥 收到回應:', data);
console.log(`✅ 已選擇 ${entries.length} 張圖片`);
```

**後端：**
```python
logger.info(f"   上傳圖片數量: {len(user_images) if user_images else 0}")
```

## 測試步驟

### 1. 測試單張衣物圖片上傳

1. 登入系統
2. 進入「穿搭小助手」頁面
3. 點擊相機按鈕上傳**1張衣物圖片**（例如：T恤）
4. 輸入「穿搭」或直接點擊發送
5. **預期結果：**
   - 前端 console 顯示：`📤 發送請求: { user_input: '穿搭', image_count: 1 }`
   - 後端日誌顯示：`上傳圖片數量: 1`
   - 後端日誌顯示：`✅ 分類結果: 衣物 (1 張)`
   - 系統執行**策略2**：用戶上傳的衣物 + 用戶頭貼
   - 返回包含上傳衣物的穿搭圖

### 2. 測試多張衣物圖片上傳

1. 上傳**2張衣物圖片**（例如：上衣 + 褲子）
2. 輸入「穿搭」
3. **預期結果：**
   - 前端 console 顯示：`image_count: 2`
   - 後端日誌顯示：`上傳圖片數量: 2`
   - 系統執行**策略2**：用戶上傳的2件衣物 + 用戶頭貼

### 3. 測試臉部圖片上傳

1. 上傳**1張臉部照片**
2. 輸入「穿搭」
3. **預期結果：**
   - 後端日誌顯示：`✅ 分類結果: 臉部 (1 張)`
   - 系統執行**策略1**：用戶上傳的臉部 + 衣櫥的2件衣物

### 4. 測試混合上傳（臉部 + 衣物）

1. 上傳**1張臉部照片 + 2張衣物圖片**（共3張）
2. 輸入「穿搭」
3. **預期結果：**
   - 後端日誌顯示：`✅ 分類結果: 臉部 (1 張), 衣物 (2 張)`
   - 系統執行**策略3**：用戶上傳的臉部 + 用戶上傳的衣物

### 5. 測試圖片數量限制

1. 嘗試上傳**4張圖片**
2. **預期結果：**
   - 前端顯示警告：`⚠️ 最多只能上傳 3 張圖片`
   - 只有前3張被選擇
   - `pendingImages` 數組長度為 3

### 6. 測試無圖片上傳（原有功能）

1. 不上傳任何圖片
2. 輸入「推薦今天的穿搭」
3. **預期結果：**
   - 後端日誌顯示：`上傳圖片數量: 0`
   - 系統執行**策略4**：用戶頭貼 + 衣櫥內現有衣物

## 四種圖片組合策略

| 策略 | 條件 | 臉部來源 | 衣物來源 | 說明 |
|------|------|----------|----------|------|
| **策略1** | 只上傳臉部 | 上傳的臉部 | 衣櫥隨機2件 | 用新臉部試穿衣櫥衣物 |
| **策略2** | 只上傳衣物 | 用戶頭貼 | 上傳的衣物 | 用自己的臉試穿新衣物 |
| **策略3** | 上傳臉部+衣物 | 上傳的臉部 | 上傳的衣物 | 完全自訂的穿搭 |
| **策略4** | 無上傳 | 用戶頭貼 | 衣櫥現有衣物 | 原有功能 |

## 日誌檢查清單

成功修復後，日誌應該顯示：

### 前端 Console

```javascript
✅ 已選擇 1 張圖片
📤 發送請求: { user_input: '穿搭', image_count: 1 }
📥 收到回應: { type: 'image', url: '...', text: '...' }
```

### 後端日誌

```
INFO:app.api.v1.chat:收到 / 請求, Payload: user_input='穿搭' user_images=['data:image/...']
INFO:app.services.fashion_advisor:   上傳圖片數量: 1
INFO:app.services.fashion_advisor:🔍 開始分類上傳的圖片...
INFO:app.services.image_classifier:🔍 開始分類圖片...
INFO:app.services.image_classifier:✅ 圖片分類結果：clothing
INFO:app.services.fashion_advisor:✅ 分類結果: 衣物 (1 張)
INFO:app.services.fashion_advisor:📋 策略決策：
INFO:app.services.fashion_advisor:   策略: 上傳衣物+用戶頭貼 (策略2)
INFO:app.services.fashion_advisor:   臉部照片來源: 用戶頭貼
INFO:app.services.fashion_advisor:   衣物來源: 上傳的衣物
```

## 常見問題排查

### Q1: 前端顯示「請先登入後再上傳圖片」

**原因：** Token 未正確保存或過期

**解決：**
1. 檢查 localStorage 中是否有 `token`
2. 重新登入
3. 確認 `getToken()` 函數正確讀取 token

### Q2: 後端仍然顯示 `user_images=None`

**原因：** 前端代碼未更新或瀏覽器緩存

**解決：**
1. 確認 `Assistant.jsx` 已保存修改
2. 重新啟動前端開發服務器：`npm run dev`
3. 清除瀏覽器緩存（Ctrl+Shift+R 強制刷新）
4. 檢查瀏覽器 DevTools > Network，查看實際發送的 payload

### Q3: 圖片上傳後沒有顯示在聊天視窗

**原因：** `pendingImages` 狀態未正確更新

**解決：**
1. 檢查 `handleFileChange()` 是否正確執行
2. 確認 `FileReader` 成功讀取圖片
3. 查看 console 是否有「圖片讀取失敗」錯誤

### Q4: 後端分類錯誤（臉部被認為是衣物）

**原因：** 圖片分類服務錯誤或圖片品質問題

**解決：**
1. 檢查 `GEMINI_API_KEY` 是否正確設定
2. 使用清晰的臉部照片（正面、光線充足）
3. 檢查後端日誌中的分類結果
4. 如果分類持續錯誤，可能需要調整 `image_classifier.py` 的 prompt

## 完成！

修復後，多圖片上傳功能應該完全正常運作，支援四種圖片組合策略。

**關鍵修改：**
- ✅ 前端參數名從 `images` 改為 `user_images`
- ✅ 移除不需要的 `image_names` 參數
- ✅ 前後端都限制最多 3 張圖片
- ✅ 新增調試日誌方便追蹤

**下一步測試：**
1. 重新啟動前端：`npm run dev`
2. 清除瀏覽器緩存
3. 按照測試步驟驗證所有四種策略
4. 檢查日誌確認參數正確傳遞
