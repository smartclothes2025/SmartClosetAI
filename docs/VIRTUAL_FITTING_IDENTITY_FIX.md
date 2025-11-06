# 虛擬試衣身份保留修復

## 問題描述

### 原始問題
1. **性別錯誤**：上傳男生照片，生成的卻是女生
2. **臉部特徵不一致**：不同女生照片生成的結果都很相似，沒有保留原照片特徵
3. **身份識別失敗**：生成的人物與原照片差異很大，無法識別為同一人

### 根本原因
原提示詞雖然要求「使用用戶的臉部特徵」，但對 AI 模型來說：
- 指令不夠明確和強烈
- 沒有明確要求「複製」用戶特徵
- 沒有強調性別保留的重要性
- 缺乏驗證檢查清單

## 解決方案

### 修改內容
修改 `app/services/image_generation.py` 中的 `_generate_with_clothing_images` 方法的提示詞。

### 關鍵改進

#### 1. **更強烈的指令語氣**
```
原來：「請仔細觀察並記住用戶的臉部特徵」
改為：「You MUST preserve their exact appearance」
```

#### 2. **明確的複製指令**
```
原來：「保持用戶的面部輪廓、五官比例、膚色、髮型等特徵」
改為：「COPY their facial features: face shape, eyes, nose, mouth, eyebrows, skin tone」
```

#### 3. **性別保留強調**
新增專門的性別準確性規則：
```
2. **GENDER ACCURACY** 🔴 CRITICAL:
   - If Image #1 shows a MALE person → Generate a MALE person
   - If Image #1 shows a FEMALE person → Generate a FEMALE person
   - DO NOT change the person's gender under any circumstances
```

#### 4. **身份識別強調**
```
原來：「這不是生成陌生人，而是生成『用戶本人穿著這些衣物』的照片」
改為：「This is NOT about creating a "similar" person - it's about showing THE SAME PERSON wearing different clothes」
```

#### 5. **驗證檢查清單**
新增明確的驗證項目：
```
⚠️ **VERIFICATION CHECKLIST**:
- [ ] Does the person have the same face as Image #1?
- [ ] Does the person have the same gender as Image #1?
- [ ] Are the clothes identical to the provided clothing images?
```

## 新提示詞結構

```
🎯 CRITICAL TASK: Virtual Try-On with User's Exact Facial Features

📸 **REFERENCE IMAGE (Image #1)**: This is the USER'S ACTUAL PHOTO. You MUST preserve their exact appearance.

⚠️ **MOST IMPORTANT RULES** (FAILURE TO FOLLOW = TASK FAILED):

1. **PRESERVE USER'S IDENTITY** 🔴 CRITICAL:
   - The person in the generated image MUST look EXACTLY like the person in Image #1
   - COPY their facial features: face shape, eyes, nose, mouth, eyebrows, skin tone
   - COPY their gender, age appearance, and overall look
   - COPY their hair color and hairstyle
   - DO NOT change their ethnicity, gender, or any facial characteristics
   - This is NOT about creating a "similar" person - it's about showing THE SAME PERSON wearing different clothes

2. **GENDER ACCURACY** 🔴 CRITICAL:
   - If Image #1 shows a MALE person → Generate a MALE person
   - If Image #1 shows a FEMALE person → Generate a FEMALE person
   - DO NOT change the person's gender under any circumstances

3. **CLOTHING ITEMS** (Images #2 onwards):
   [衣物清單]

4. **CLOTHING REQUIREMENTS**:
   - Study each clothing image carefully (color, pattern, texture, cut)
   - The person MUST wear clothes that look EXACTLY like these images
   - DO NOT create new designs or change colors/patterns
   - DO NOT merge multiple items into one piece

5. **OUTFIT COMPOSITION**:
   - Tops → upper body
   - Bottoms (pants/skirts) → lower body
   - Dresses → single piece outfit
   - Outerwear → outermost layer
   - Shoes → on feet
   - Accessories → appropriately placed

6. **VISUAL PRESENTATION**:
   - Natural, elegant pose
   - Full body shot showing all clothing details
   - Simple background (solid color or minimal scene)
   - Soft, natural lighting
   - High resolution, professional photography quality

7. **USER'S ADDITIONAL REQUEST**: [用戶需求]

🎯 **TASK SUMMARY**: Generate a photo of THE EXACT SAME PERSON from Image #1 wearing the exact clothes from the subsequent images. This person must be recognizable as the same individual - same face, same gender, same overall appearance.

⚠️ **VERIFICATION CHECKLIST**:
- [ ] Does the person have the same face as Image #1?
- [ ] Does the person have the same gender as Image #1?
- [ ] Are the clothes identical to the provided clothing images?
```

## 改進重點

### 語言選擇
- 使用英文提示詞（Gemini 對英文指令的理解更準確）
- 使用強烈的命令語氣（MUST, DO NOT, CRITICAL）
- 使用大寫強調關鍵要求

### 結構優化
1. **明確標註參考圖片**：「Image #1」清楚指出哪張是用戶照片
2. **優先級標示**：使用 🔴 CRITICAL 標記最重要的規則
3. **任務摘要**：在最後提供簡潔的任務總結
4. **驗證清單**：提供可檢查的項目

### 指令明確性
- 從「保持特徵」改為「複製特徵」（COPY）
- 從「相同」改為「完全相同」（EXACTLY）
- 明確列出要複製的具體特徵（face shape, eyes, nose, mouth...）

## 測試建議

### 測試案例
1. **男性照片** + 女性服裝 → 應生成男性穿著這些服裝
2. **不同女性照片** → 應生成各自不同的女性，保留各自特徵
3. **不同年齡** → 應保留原照片的年齡外觀
4. **不同種族** → 應保留原照片的種族特徵

### 驗證標準
生成的圖片應該：
- ✅ 性別與原照片一致
- ✅ 臉部特徵可識別為同一人
- ✅ 膚色、髮型與原照片相似
- ✅ 年齡外觀與原照片相符
- ✅ 衣物與提供的圖片一致

## 技術限制

### Gemini 2.5 Flash Image 的能力
- ✅ 可以理解和參考多張圖片
- ✅ 可以進行 Image-to-Image 生成
- ⚠️ 臉部特徵保留的準確度取決於提示詞質量
- ⚠️ 可能無法 100% 完美複製臉部特徵

### 預期效果
- **改進前**：生成的人物與原照片完全不同
- **改進後**：生成的人物應該能識別為同一人，主要特徵（性別、臉型、膚色）應該一致
- **理想狀態**：生成的人物看起來就像原照片中的人換了衣服

## 後續優化方向

如果效果仍不理想，可以考慮：

1. **使用更專業的模型**
   - 考慮使用專門的虛擬試衣模型（如 IDM-VTON, StableVITON）
   - 這些模型專門訓練用於保留人物特徵

2. **增加臉部檢測**
   - 先使用臉部檢測 API 提取用戶臉部特徵
   - 在提示詞中加入更詳細的臉部描述

3. **多步驟生成**
   - 第一步：生成基礎試穿圖
   - 第二步：使用臉部替換技術將用戶臉部合成到圖片中

4. **提供更多參考**
   - 要求用戶提供多角度照片
   - 使用多張照片增強特徵識別

## 修改記錄

- **2024-11-06**: 初始修復，重寫提示詞以強化身份保留
  - 修改檔案：`app/services/image_generation.py`
  - 修改方法：`_generate_with_clothing_images`
  - 主要改進：使用更強烈的英文指令、明確的複製要求、性別保留強調
