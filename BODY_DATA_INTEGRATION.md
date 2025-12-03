# 虛擬試衣整合身體數據功能說明

## 📋 功能概述

SmartClosetAI 專案已成功整合用戶身體數據（身形類型和 BMI）到虛擬試衣功能中，讓 AI 生成的穿搭圖更符合用戶的實際體型。

## ✨ 主要功能

### 1. 自動獲取用戶身體數據

當用戶生成穿搭圖時，系統會自動從資料庫讀取：
- **身高和體重** → 計算 BMI
- **胸圍、腰圍、臀圍、肩寬** → 判斷身形類型

### 2. 智能身形判斷

**女性身形類型**（按優先順序）：
1. **沙漏型身材**：胸圍-腰圍 12-28 cm，臀圍-腰圍 15-33 cm，胸臀差 ≤ 7 cm
2. **倒三角身材**：肩寬×2 - 臀圍 > 5 cm
3. **梨型身材**：臀圍 - 肩寬×2 > 5 cm 且 臀圍 > 胸圍 + 3 cm
4. **H型身材**：胸圍-腰圍 < 15 cm 或 臀圍-腰圍 < 20 cm
5. **蘋果型身材**：腰圍 > 臀圍

**男性身形類型**：
1. **蘋果型身材**：腰圍 > 臀圍
2. **梨型身材**：臀圍 - 肩寬×2 > 3 cm
3. **倒三角身材**：肩寬×2 - 臀圍 > 3 cm
4. **H型身材**：肩寬×2 與 臀圍 差異 < 3 cm

### 3. BMI 分類

- **體重過輕**：BMI < 18.5
- **正常範圍**：18.5 ≤ BMI < 24
- **過重**：24 ≤ BMI < 27
- **輕度肥胖**：27 ≤ BMI < 30
- **中度肥胖**：BMI ≥ 30

### 4. AI Prompt 整合

系統會將身形類型和 BMI 轉換為英文描述，整合到 AI 生成的 prompt 中：

**身形類型映射**：
- 沙漏型 → `hourglass body shape with balanced bust and hip proportions, defined waist`
- 梨型 → `pear body shape with fuller hips and thighs, narrower shoulders`
- 倒三角 → `inverted triangle body shape with broader shoulders, narrower hips`
- H型 → `rectangular body shape with straight silhouette, minimal waist definition`
- 蘋果型 → `apple body shape with fuller midsection, rounded torso`

**BMI 映射**：
- 體重過輕 → `slim and lean build`
- 正常範圍 → `healthy and fit physique`
- 過重 → `slightly fuller build`
- 輕度肥胖 → `fuller figure`
- 中度肥胖 → `plus-size build`

## 🔧 技術實作

### 後端修改

**檔案**：`app/api/v1/virtual_fitting.py`

**新增功能**（第 132-223 行）：
```python
# ✨ 獲取用戶身體數據（身形類型和 BMI）
body_data = None
body_shape_type = None
bmi_value = None
bmi_category = None

try:
    # 從 body_metrics 表查詢用戶身體數據
    body_metrics_query = text("""
        SELECT height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, sex
        FROM body_metrics
        WHERE user_id = :user_id
        LIMIT 1
    """)
    result = db.execute(body_metrics_query, {"user_id": current_user.id})
    body_metrics = result.mappings().first()
    
    if body_metrics:
        # 計算 BMI
        if height_cm and weight_kg and height_cm > 0:
            height_m = height_cm / 100
            bmi_value = round(weight_kg / (height_m * height_m), 1)
            # BMI 分類...
        
        # 判斷身形類型（女性/男性）
        if sex == '女' and all([chest_cm, waist_cm, hip_cm, shoulder_cm]):
            # 按照前端相同的判斷順序
            if (diff_bw >= 12 and diff_bw <= 28) and (diff_hw >= 15 and diff_hw <= 33) and (diff_bh <= 7):
                body_shape_type = '沙漏型身材'
            # ...其他判斷邏輯
except Exception as e:
    logger.warning(f"獲取身體數據失敗: {e}，將不使用身體數據生成")
```

**傳遞給 AI 服務**（第 253-261 行）：
```python
# 建立 prompt（整合身體數據）
prompt = image_service.create_fashion_prompt(
    clothing_items=items_dict,
    user_input=request.user_input,
    style="casual",
    body_shape_type=body_shape_type,
    bmi_value=bmi_value,
    bmi_category=bmi_category,
)
```

**返回生成資訊**（第 327-338 行）：
```python
# 組合生成資訊
generation_info_parts = [
    f"✅ 使用 {clothing_images_used} 張實際衣物圖片生成 (Image-to-Image)",
    f"📸 照片來源: {photo_source}"
]

if body_shape_type:
    generation_info_parts.append(f"👤 身形類型: {body_shape_type}")
if bmi_value and bmi_category:
    generation_info_parts.append(f"📊 BMI: {bmi_value} ({bmi_category})")

generation_info = "\n".join(generation_info_parts)
```

### AI 服務修改

**檔案**：`app/services/image_generation.py`

**更新 prompt 生成函數**（第 552-642 行）：
```python
def create_fashion_prompt(
    self,
    clothing_items: list,
    user_input: str,
    style: str = "casual",
    body_shape_type: Optional[str] = None,
    bmi_value: Optional[float] = None,
    bmi_category: Optional[str] = None
) -> str:
    """
    Create optimized prompt for fashion image generation
    整合用戶身體數據（身形類型和 BMI）
    """
    # 構建身體特徵描述
    body_description_parts = []
    
    # 身形類型映射到英文描述
    if body_shape_type and body_shape_type in body_shape_map:
        body_description_parts.append(body_shape_map[body_shape_type])
        logger.info(f"✨ 使用身形類型: {body_shape_type} -> {body_shape_map[body_shape_type]}")
    
    # BMI 映射到體型描述
    if bmi_value and bmi_category:
        if bmi_category in bmi_description_map:
            body_description_parts.append(bmi_description_map[bmi_category])
            logger.info(f"✨ 使用 BMI: {bmi_value} ({bmi_category}) -> {bmi_description_map[bmi_category]}")
    
    # 組合身體描述
    body_description = ", ".join(body_description_parts) if body_description_parts else "natural body proportions"
    
    # Create comprehensive prompt（整合身體數據）
    prompt = f"""A Asian Taiwanese person with {body_description}, wearing {clothing_text}, 
    East Asian facial features,
    natural Asian skin tone,
    standing in a modern minimalist studio, 
    soft natural lighting, neutral background, 
    full body shot showing the complete outfit and body proportions,
    relaxed and casual pose that flatters the body shape,
    detailed clothing texture, realistic fabric that fits the body naturally,
    high facial realism and detail is critical,
    clothing should fit and drape naturally on the body type"""
    
    return prompt
```

### 前端修改

**檔案**：`src/pages/VirtualFitting.jsx`

**新增狀態**（第 48 行）：
```javascript
const [generationInfo, setGenerationInfo] = useState(null);
```

**保存生成資訊**（第 166-169 行）：
```javascript
if (result.type === "image" && result.url) {
  setGeneratedImageUrl(result.url);
  // 保存生成資訊（包含身形、BMI 等）
  if (result.text) {
    setGenerationInfo(result.text);
  }
}
```

**生成中提示**（第 347-349 行）：
```jsx
<p className="text-xs text-indigo-600 mt-3 font-medium">
  ✨ 正在結合您的身形和 BMI 數據生成
</p>
```

**顯示生成資訊**（第 377-383 行）：
```jsx
{generationInfo && (
  <div className="mt-3 p-3 bg-white rounded-lg border border-indigo-200 text-xs">
    <div className="text-gray-700 whitespace-pre-line">
      {generationInfo}
    </div>
  </div>
)}
```

## 📊 使用流程

```
用戶進入虛擬試衣頁面
    ↓
1. 選擇衣物並上傳照片
    ↓
2. 點擊生成穿搭圖
    ↓
3. 後端自動查詢用戶身體數據
    ├─ 從 body_metrics 表讀取身高、體重、三圍、肩寬
    ├─ 計算 BMI 和判斷身形類型
    └─ 記錄到日誌
    ↓
4. 將身體數據整合到 AI prompt
    ├─ 身形類型 → 英文描述
    ├─ BMI 分類 → 體型描述
    └─ 組合成完整 prompt
    ↓
5. 調用 Gemini AI 生成穿搭圖
    ├─ 使用用戶照片（臉部特徵）
    ├─ 使用衣物圖片
    └─ 使用身體數據（體型特徵）
    ↓
6. 返回生成結果
    ├─ 穿搭圖片
    └─ 生成資訊（包含身形類型和 BMI）
    ↓
7. 前端顯示
    ├─ 穿搭圖片
    └─ 生成資訊卡片
```

## 🎯 效果展示

**生成中提示**：
```
AI 正在生成逼真穿搭圖...
這可能需要 10 - 30 秒
✨ 正在結合您的身形和 BMI 數據生成
```

**生成資訊卡片**：
```
✅ 使用 3 張實際衣物圖片生成 (Image-to-Image)
📸 照片來源: 用戶上傳照片
👤 身形類型: 沙漏型身材
📊 BMI: 21.5 (正常範圍)
```

## 🔍 日誌輸出

**後端日誌**：
```
INFO: 收到虛擬試衣請求：3 件衣物
INFO: 用戶 BMI: 21.5 (正常範圍)
INFO: 用戶身形類型: 沙漏型身材
INFO: ✨ 使用身形類型: 沙漏型身材 -> hourglass body shape with balanced bust and hip proportions, defined waist
INFO: ✨ 使用 BMI: 21.5 (正常範圍) -> healthy and fit physique
INFO: 圖片生成成功，返回 base64 數據
INFO: 使用衣物圖片數量: 3
INFO: 照片來源: 用戶上傳照片
```

## ⚙️ 降級機制

如果用戶尚未填寫身體數據：
- ✅ 系統會自動降級，不使用身體數據
- ✅ 仍然可以正常生成穿搭圖
- ✅ 日誌會記錄：`獲取身體數據失敗，將不使用身體數據生成`

## 🧪 測試方式

1. **填寫身體數據**：
   - 進入「身材分析」頁面
   - 填寫身高、體重、胸圍、腰圍、臀圍、肩寬
   - 保存數據

2. **生成穿搭圖**：
   - 進入「衣櫥」頁面
   - 選擇 2-3 件衣物
   - 點擊「虛擬試衣」
   - 上傳照片
   - 等待生成

3. **檢查結果**：
   - 查看生成的穿搭圖
   - 檢查生成資訊卡片是否顯示身形類型和 BMI
   - 打開後端日誌確認數據已被使用

## 📈 優勢

1. **個性化**：根據用戶實際體型生成穿搭圖
2. **準確性**：AI 能更好地理解用戶的身材比例
3. **真實感**：生成的穿搭圖更符合用戶實際外觀
4. **透明度**：用戶可以看到系統使用了哪些身體數據
5. **穩定性**：完整的降級機制，即使沒有身體數據也能正常使用

## 🔄 與前端身材分析的一致性

後端的身形判斷邏輯與前端 `src/components/wardrobe/Analysis.jsx` 完全一致：
- ✅ 相同的判斷順序（沙漏型 → 倒三角 → 梨型 → H型 → 蘋果型）
- ✅ 相同的數值標準（胸圍-腰圍 12-28 cm，臀圍-腰圍 15-33 cm 等）
- ✅ 相同的 BMI 分類標準

## 📝 相關檔案

**後端**：
- `app/api/v1/virtual_fitting.py` - 虛擬試衣 API（獲取身體數據）
- `app/services/image_generation.py` - AI 圖片生成服務（整合身體數據到 prompt）

**前端**：
- `src/pages/VirtualFitting.jsx` - 虛擬試衣頁面（顯示生成資訊）
- `src/components/wardrobe/Analysis.jsx` - 身材分析頁面（身形判斷邏輯）

**資料庫**：
- `body_metrics` 表 - 儲存用戶身體數據

## 🎉 完成日期

2025-12-03

---

**現在生成穿搭圖時，AI 會同時考慮用戶的頭像、身形類型和 BMI，生成更符合用戶實際體型的穿搭效果！** ✨
