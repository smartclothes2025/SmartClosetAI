# 虛擬試穿功能 - 基於實際衣物圖片

## 問題描述

### 原始問題
用戶選擇了特定的衣物（例如：skirt 和 top1），但 AI 生成的圖片顯示的是完全不同的服裝（例如：白色連衣裙），與用戶選擇的衣物不符。

### 根本原因
之前的實現只使用**文字描述**來生成圖片：
- 只傳遞衣物的名稱和類別
- AI 根據文字描述自由創作
- 無法保證生成的圖片與實際衣物相符

## 解決方案

### 新功能：基於實際衣物圖片的虛擬試穿

現在系統會：
1. ✅ 獲取用戶選擇的衣物的**實際圖片 URL**
2. ✅ 下載這些衣物圖片
3. ✅ 將圖片和文字提示一起傳給 Gemini 2.5 Flash Image
4. ✅ AI 根據實際衣物圖片生成虛擬試穿效果

### 技術實現

#### 1. 多模態輸入
使用 Gemini 2.5 Flash Image 的多模態能力：
- **文字提示**：描述虛擬試穿要求
- **圖片輸入**：實際的衣物圖片

#### 2. 新增方法
**檔案**: `app/services/image_generation.py`

```python
async def _generate_with_clothing_images(
    self, 
    prompt: str, 
    clothing_items: List[Dict]
) -> Dict[str, Any]:
    """
    使用實際衣物圖片進行虛擬試穿
    """
    # 準備內容：文字 + 圖片
    content_parts = [enhanced_prompt]
    
    # 下載並添加每件衣物的圖片
    for item in clothing_items:
        img_url = item.get('img')
        if img_url:
            # 下載圖片
            response = requests.get(img_url)
            img = Image.open(BytesIO(response.content))
            
            # 添加到內容
            content_parts.append({
                "mime_type": "image/jpeg",
                "data": img_bytes
            })
    
    # 生成虛擬試穿圖片
    response = model.generate_content(content_parts)
```

#### 3. 增強的提示詞

```
請根據以下衣物圖片，生成一張專業的虛擬試穿效果圖：

要求：
1. 將提供的所有衣物圖片中的服裝穿在同一位模特兒身上
2. 保持每件衣物的原始顏色、圖案和質感
3. 確保服裝搭配自然協調
4. 模特兒姿態專業自然
5. 背景簡潔時尚
6. 專業時尚攝影風格
7. 高清晰度
```

### 工作流程

```
用戶選擇衣物
    ↓
前端傳送衣物數據（包含圖片 URL）
    ↓
後端 API 接收請求
    ↓
圖片生成服務下載衣物圖片
    ↓
將圖片 + 文字提示傳給 Gemini
    ↓
Gemini 生成虛擬試穿圖片
    ↓
返回給前端顯示
```

## 修改的檔案

### 1. `app/services/image_generation.py`
- ✅ 添加 `clothing_items` 參數到 `generate_tryon_image()`
- ✅ 新增 `_generate_with_clothing_images()` 方法
- ✅ 實現圖片下載和處理邏輯
- ✅ 添加詳細的日誌記錄

### 2. `app/api/v1/virtual_fitting.py`
- ✅ 將 `items_dict` 傳遞給圖片生成服務
- ✅ 添加日誌記錄衣物數量

## 測試

### 測試腳本
```bash
python test_virtual_fitting_with_images.py
```

### 測試數據範例
```json
{
  "user_input": "休閒時尚穿搭",
  "selected_items": [
    {
      "id": "test-top-1",
      "name": "白色T恤",
      "category": "上衣",
      "img": "https://storage.googleapis.com/.../top1.jpg"
    },
    {
      "id": "test-skirt-1",
      "name": "牛仔裙",
      "category": "裙子",
      "img": "https://storage.googleapis.com/.../skirt.jpg"
    }
  ]
}
```

## 預期效果

### 之前（純文字）
- ❌ 生成的圖片與選擇的衣物不符
- ❌ AI 自由創作，無法控制
- ❌ 顏色、款式可能完全不同

### 現在（基於圖片）
- ✅ 生成的圖片使用實際選擇的衣物
- ✅ 保持原始顏色和款式
- ✅ 準確反映用戶選擇

## 日誌輸出

系統會記錄詳細的處理過程：

```
INFO - 開始生成圖片，使用提示詞長度：XXX 字元
INFO - 傳遞 2 件衣物數據到圖片生成服務
INFO - 正在下載衣物圖片: 白色T恤 from https://...
INFO - 成功載入衣物圖片: 白色T恤
INFO - 正在下載衣物圖片: 牛仔裙 from https://...
INFO - 成功載入衣物圖片: 牛仔裙
INFO - 總共載入 2 張衣物圖片，開始生成虛擬試穿圖
INFO - 虛擬試穿圖片生成成功
```

## 後備機制

如果衣物圖片載入失敗，系統會自動回退：
1. 嘗試使用實際衣物圖片 ✅
2. 失敗 → 使用純文字生成 ⚠️
3. 失敗 → 使用 Imagen (需要 GCP) ⚠️
4. 失敗 → 返回文字描述 ℹ️

## 注意事項

### 圖片要求
- 支援的格式：JPEG, PNG
- 自動調整大小：最大 1024x1024
- 自動轉換為 RGB 模式

### 性能考量
- 下載超時：10 秒
- 圖片處理：自動壓縮
- 生成時間：約 10-30 秒（取決於衣物數量）

### 錯誤處理
- 圖片下載失敗：記錄警告，繼續處理其他圖片
- 所有圖片失敗：回退到純文字生成
- 網路超時：返回錯誤訊息

## 總結

現在虛擬試穿功能使用**實際的衣物圖片**進行生成，確保：
- ✅ 生成的圖片與用戶選擇的衣物一致
- ✅ 保持原始顏色和款式
- ✅ 提供更準確的虛擬試穿體驗

這解決了「生成的圖片跟選取的圖片不同」的問題！
