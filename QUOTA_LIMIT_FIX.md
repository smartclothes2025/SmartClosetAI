# Gemini API 配額限制解決方案

## 📋 問題描述

使用 `gemini-2.5-flash-image` 模型時遇到免費配額限制錯誤：

```
RESOURCE_EXHAUSTED: generativelanguage.googleapis.com/generate_content_free_tier_requests
quota_metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count
```

**錯誤原因**：
- 免費版每天請求次數限制
- 免費版每分鐘請求次數限制
- 免費版每分鐘輸入 token 數量限制

## ✅ 解決方案

### 1. 自動模型降級機制

當 `gemini-2.5-flash-image` 達到配額限制時，系統會自動降級到 `gemini-1.5-flash`。

**實作邏輯**：
```python
# 嘗試使用的模型列表（按優先級排序）
models_to_try = [
    'gemini-2.5-flash-image',  # 優先使用 2.5
    'gemini-1.5-flash',         # 降級到 1.5
]
```

### 2. 智能錯誤檢測

系統會自動檢測配額限制錯誤：
```python
is_quota_error = (
    "quota" in error_msg.lower() or 
    "rate limit" in error_msg.lower() or
    "RESOURCE_EXHAUSTED" in error_msg or
    "free_tier" in error_msg.lower()
)
```

### 3. 重試機制

**配額錯誤處理流程**：
```
遇到配額錯誤
    ↓
檢查是否有下一個模型
    ├─ 有 → 降級到下一個模型（gemini-1.5-flash）
    └─ 沒有 → 等待後重試
    ↓
重試 3 次
    ├─ 成功 → 返回結果
    └─ 失敗 → 拋出錯誤
```

## 🔧 技術實作

**檔案**：`app/services/image_generation.py`

**修改位置**：第 177-535 行

### 關鍵代碼

**1. 模型列表定義**（第 177-184 行）：
```python
# 嘗試使用的模型列表（按優先級排序）
models_to_try = [
    'gemini-2.5-flash-image',  # 優先使用 2.5
    'gemini-1.5-flash',         # 降級到 1.5
]

model_name = models_to_try[0]  # 預設使用第一個
model = genai.GenerativeModel(model_name)
```

**2. 配額錯誤檢測與降級**（第 496-523 行）：
```python
# 檢查是否是配額限制錯誤
is_quota_error = (
    "quota" in error_msg.lower() or 
    "rate limit" in error_msg.lower() or
    "RESOURCE_EXHAUSTED" in error_msg or
    "free_tier" in error_msg.lower()
)

if is_quota_error:
    logger.warning(f"   ⚠️ 檢測到配額限制錯誤")
    
    # 嘗試降級到下一個模型
    if current_model_index + 1 < len(models_to_try):
        current_model_index += 1
        model_name = models_to_try[current_model_index]
        model = genai.GenerativeModel(model_name)
        logger.info(f"   🔄 降級到模型: {model_name}")
        continue
    else:
        logger.error(f"   ❌ 所有模型都達到配額限制")
        # 如果是最後一次嘗試，拋出異常
        if attempt == max_retries - 1:
            raise
        # 等待後重試
        wait_time = retry_delay * (attempt + 1)
        logger.info(f"   ⏳ 等待 {wait_time} 秒後重試...")
        await asyncio.sleep(wait_time)
        continue
```

**3. 返回使用的模型資訊**（第 557-566 行）：
```python
return {
    "success": True,
    "image_base64": image_base64,
    "format": "base64",
    "prompt": prompt,
    "service": f"{model_name}-with-clothing",
    "clothing_images_used": clothing_images_loaded,
    "method": "multimodal_with_actual_clothing_images",
    "model_used": model_name  # 記錄實際使用的模型
}
```

## 📊 處理流程

```
用戶請求生成穿搭圖
    ↓
1. 使用 gemini-2.5-flash-image
    ├─ 成功 → 返回結果 ✅
    └─ 配額限制錯誤 ↓
    
2. 自動降級到 gemini-1.5-flash
    ├─ 成功 → 返回結果 ✅
    └─ 仍然配額限制 ↓
    
3. 等待 2 秒後重試
    ├─ 成功 → 返回結果 ✅
    └─ 仍然失敗 ↓
    
4. 等待 4 秒後重試
    ├─ 成功 → 返回結果 ✅
    └─ 仍然失敗 ↓
    
5. 等待 6 秒後重試
    ├─ 成功 → 返回結果 ✅
    └─ 失敗 → 拋出錯誤 ❌
```

## 🔍 日誌輸出

**正常流程**：
```
INFO: 🚀 開始調用 Gemini 模型: gemini-2.5-flash-image
INFO:    內容部分數量: 4 (1 prompt + 3 images)
INFO: ✅ 模型回應已接收,正在檢查結果...
INFO:    圖片大小: 245.3 KB
INFO:    使用衣物圖片: 3 張
```

**配額限制 + 降級流程**：
```
INFO: 🚀 開始調用 Gemini 模型: gemini-2.5-flash-image
WARNING: ⚠️ 嘗試 1/3 失敗: RESOURCE_EXHAUSTED: quota exceeded
WARNING:    ⚠️ 檢測到配額限制錯誤
INFO:    🔄 降級到模型: gemini-1.5-flash
INFO: ✅ 模型回應已接收,正在檢查結果...
INFO:    圖片大小: 198.7 KB
INFO:    使用衣物圖片: 3 張
```

**所有模型都達到配額**：
```
INFO: 🚀 開始調用 Gemini 模型: gemini-2.5-flash-image
WARNING: ⚠️ 嘗試 1/3 失敗: RESOURCE_EXHAUSTED: quota exceeded
WARNING:    ⚠️ 檢測到配額限制錯誤
INFO:    🔄 降級到模型: gemini-1.5-flash
WARNING: ⚠️ 嘗試 2/3 失敗: RESOURCE_EXHAUSTED: quota exceeded
WARNING:    ⚠️ 檢測到配額限制錯誤
ERROR:    ❌ 所有模型都達到配額限制
INFO:    ⏳ 等待 4 秒後重試...
INFO: 🔄 重試第 3/3 次...
```

## 💡 建議

### 短期解決方案

1. **使用降級機制**（已實作）：
   - 自動從 `gemini-2.5-flash-image` 降級到 `gemini-1.5-flash`
   - 降低 API 調用頻率

2. **等待配額重置**：
   - 免費版每天配額會在 UTC 時間 00:00 重置
   - 免費版每分鐘配額會在每分鐘重置

### 長期解決方案

1. **升級到付費版**：
   - 付費版有更高的配額限制
   - 更穩定的服務品質
   - 參考：https://ai.google.dev/pricing

2. **實作請求排隊機制**：
   - 限制同時請求數量
   - 實作請求隊列
   - 避免短時間內大量請求

3. **快取機制**：
   - 快取已生成的穿搭圖
   - 相同衣物組合直接返回快取結果
   - 減少 API 調用次數

## 🎯 配額限制參考

**Gemini 免費版限制**（2024年數據）：

| 模型 | 每分鐘請求 | 每天請求 | 每分鐘 Token |
|------|-----------|---------|-------------|
| gemini-2.5-flash-image | 15 | 1,500 | 1,000,000 |
| gemini-1.5-flash | 15 | 1,500 | 1,000,000 |

**付費版限制**：
- 每分鐘請求：1,000+
- 每天請求：無限制
- 每分鐘 Token：4,000,000+

## ⚙️ 環境變數

確保已設定：
```bash
GEMINI_API_KEY=your_api_key_here
```

## 🧪 測試方式

1. **觸發配額限制**：
   - 短時間內多次生成穿搭圖
   - 觀察日誌輸出

2. **檢查降級機制**：
   - 查看日誌是否顯示「降級到模型: gemini-1.5-flash」
   - 確認仍能成功生成穿搭圖

3. **檢查重試機制**：
   - 查看日誌是否顯示「等待 X 秒後重試」
   - 確認最終成功或失敗

## 📈 優勢

1. **自動降級**：無需手動干預，自動切換模型
2. **智能重試**：根據錯誤類型決定重試策略
3. **透明日誌**：清楚記錄每一步操作
4. **穩定性**：即使達到配額限制，仍有機會成功生成
5. **用戶體驗**：用戶無感知，系統自動處理

## 🔄 更新日期

2025-12-03

---

**現在系統會自動處理 Gemini API 配額限制，並降級到其他可用模型，確保服務穩定性！** ✨
