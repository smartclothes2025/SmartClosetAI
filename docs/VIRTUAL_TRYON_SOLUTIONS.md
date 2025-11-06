# 虛擬試穿解決方案分析

## 問題診斷

### 當前實現的局限性

#### 1. 模型不適合
- **使用**: `gemini-2.5-flash-image`
- **類型**: 多模態理解模型
- **能力**: 圖片理解、簡單編輯
- **局限**: ❌ 不支援精確的虛擬試穿

#### 2. 缺少關鍵組件
真正的虛擬試穿需要：
- ❌ 人像分割（Person Segmentation）
- ❌ 服裝分割（Garment Segmentation）
- ❌ 形狀適應（Garment Warping）
- ❌ 圖像替換（Inpainting）
- ❌ 姿態估計（Pose Estimation）

#### 3. 提示詞局限
- 缺少基礎人像圖片
- 模型必須同時創造模特兒和穿衣服
- 文字權重可能高於圖片權重

## 專業虛擬試穿解決方案

### 方案 A：使用專業 VTON API

#### 1. Replicate - Virtual Try-On Models
```python
# 使用 IDM-VTON 或 OOTDiffusion
import replicate

output = replicate.run(
    "cuuupid/idm-vton:c871bb9b046607b680449ecbae55fd8c6d945e0a1948644bf2361b3d021d3ff4",
    input={
        "garm_img": "https://.../top1.jpg",  # 衣物圖片
        "human_img": "https://.../model.jpg",  # 人像圖片
        "garment_des": "white t-shirt"
    }
)
```

**優點**：
- ✅ 專業虛擬試穿模型
- ✅ 高精度服裝替換
- ✅ 保持衣物細節
- ✅ API 簡單易用

**成本**：約 $0.01-0.05 per image

#### 2. Hugging Face - Virtual Try-On Models
```python
# 使用 Diffusers 的 VTON 模型
from diffusers import StableDiffusionInpaintPipeline

# 可用模型：
# - yisol/IDM-VTON
# - levihsu/OOTDiffusion
# - aimagelab/viton-hd
```

#### 3. Google Vertex AI - Imagen with Inpainting
```python
# 使用 Imagen 的 Inpainting 功能
from vertexai.preview.vision_models import ImageGenerationModel

model = ImageGenerationModel.from_pretrained("imagegeneration@006")
images = model.edit_image(
    base_image=base_image,  # 人像
    mask=mask,  # 需要替換的區域
    prompt="wearing white t-shirt and blue skirt",
    edit_mode="inpainting-insert"
)
```

### 方案 B：改進當前實現（臨時方案）

如果暫時無法使用專業 VTON API，可以改進提示詞：

#### 1. 添加基礎人像
```python
async def _generate_with_clothing_images_improved(
    self, 
    prompt: str, 
    clothing_items: List[Dict],
    base_model_image: Optional[str] = None  # 新增：基礎模特兒圖片
):
    content_parts = []
    
    # 如果有基礎人像，先添加
    if base_model_image:
        content_parts.append({
            "mime_type": "image/jpeg",
            "data": base_model_image_bytes
        })
        
        tryon_prompt = f"""請將以下衣物圖片中的服裝替換到第一張人像圖片的模特兒身上：

要求：
1. 保持人像的姿態和背景不變
2. 只替換衣物部分
3. 保持衣物的原始顏色、圖案和質感
4. 確保服裝與身體自然貼合
5. 保持光線和陰影一致

衣物圖片如下："""
    else:
        # 沒有基礎人像，生成新的
        tryon_prompt = f"""請生成一張專業模特兒穿著以下衣物的圖片：

要求：
1. 使用專業時尚模特兒（亞洲女性，身材標準）
2. 嚴格按照提供的衣物圖片的外觀（顏色、圖案、款式）
3. 不要創造新的服裝，必須使用提供的圖片
4. 每件衣物都要清晰可見
5. 專業攝影風格

衣物圖片如下："""
```

#### 2. 改進圖片順序和標註
```python
# 為每件衣物添加明確標註
for idx, item in enumerate(clothing_items, 1):
    content_parts.append(f"\n第 {idx} 件衣物 - {item['category']}: {item['name']}")
    content_parts.append({
        "mime_type": "image/jpeg",
        "data": img_bytes
    })
```

#### 3. 使用更強的模型
```python
# 嘗試使用 Gemini 2.0 Pro 或其他更強的模型
model = genai.GenerativeModel('gemini-2.0-pro-exp')
```

### 方案 C：混合方案（最實用）

結合多種技術：

```python
async def generate_tryon_image_hybrid(
    self,
    prompt: str,
    clothing_items: List[Dict],
    user_photo: Optional[str] = None
):
    """
    混合虛擬試穿方案
    """
    
    # 1. 優先：如果有專業 VTON API
    if self.replicate_api_key and user_photo:
        try:
            return await self._generate_with_replicate_vton(
                user_photo, clothing_items
            )
        except Exception as e:
            logger.warning(f"Replicate VTON failed: {e}")
    
    # 2. 次選：使用 Imagen Inpainting
    if self.gcp_project_id and user_photo:
        try:
            return await self._generate_with_imagen_inpainting(
                user_photo, clothing_items
            )
        except Exception as e:
            logger.warning(f"Imagen inpainting failed: {e}")
    
    # 3. 後備：改進的 Gemini 生成
    if self.gemini_api_key:
        try:
            return await self._generate_with_gemini_improved(
                prompt, clothing_items, user_photo
            )
        except Exception as e:
            logger.warning(f"Gemini generation failed: {e}")
    
    # 4. 最終：文字描述
    return await self._generate_description_with_gemini(prompt)
```

## 推薦實施步驟

### 短期（1-2天）
1. ✅ 改進提示詞（方案 B）
2. ✅ 添加基礎模特兒圖片庫
3. ✅ 優化圖片標註

### 中期（1週）
1. 🔧 整合 Replicate VTON API
2. 🔧 實現混合方案
3. 🔧 添加用戶照片上傳

### 長期（1個月）
1. 🎯 訓練自己的 VTON 模型
2. 🎯 優化性能和成本
3. 🎯 添加高級功能（姿態調整等）

## 成本分析

| 方案 | 成本/圖片 | 質量 | 速度 |
|------|----------|------|------|
| Gemini 2.5 Flash Image | $0.002 | ⭐⭐ | 快 |
| Replicate VTON | $0.01-0.05 | ⭐⭐⭐⭐⭐ | 中 |
| Vertex AI Imagen | $0.02-0.04 | ⭐⭐⭐⭐ | 中 |
| 自建模型 | 固定成本 | ⭐⭐⭐⭐ | 快 |

## 結論

**當前問題**：使用了不適合的模型（多模態理解 vs 虛擬試穿）

**最佳解決方案**：
1. **立即**：改進提示詞和添加基礎模特兒圖片（方案 B）
2. **短期**：整合專業 VTON API（方案 A - Replicate）
3. **長期**：實現混合方案（方案 C）

**預期效果**：
- 提示詞改進：準確度提升 30-50%
- 專業 VTON API：準確度提升 80-95%
- 混合方案：最佳平衡（質量、成本、速度）
