# 虛擬試穿功能簡化說明

## 修改摘要

已將虛擬試穿功能簡化，**移除所有身體數據輸入**，只需要照片即可使用。

## 主要變更

### 1. API 模型修改

**檔案**: `app/api/v1/virtual_fitting.py`

#### ClothingItem 模型
- ✅ 將 `id` 欄位從 `int` 改為 `str`，支援 UUID 格式
- ✅ 保留 `name`, `category`, `img` 欄位

```python
class ClothingItem(BaseModel):
    id: str  # 支援 UUID 字串
    name: str
    category: str
    img: Optional[str] = None
```

#### VirtualFittingRequest 模型
- ❌ 移除 `body_metrics` 參數
- ✅ 保留 `user_input`, `selected_items`, `user_photo`

```python
class VirtualFittingRequest(BaseModel):
    user_input: str
    selected_items: List[ClothingItem]
    user_photo: Optional[str] = None  # Base64 encoded user photo
```

### 2. 圖片生成服務修改

**檔案**: `app/services/image_generation.py`

#### create_fashion_prompt 方法
- ❌ 移除 `body_metrics` 參數及相關邏輯
- ✅ 簡化提示詞生成，不再包含身體特徵描述

```python
def create_fashion_prompt(
    self,
    clothing_items: list,
    user_input: str,
    style: str = "casual"
) -> str:
    """
    Create optimized prompt for fashion image generation
    只需要照片，不需要身體數據
    """
```

### 3. 提示詞生成邏輯
- 移除身高、體重、BMI 計算
- 移除體型描述（slim build, athletic build 等）
- 使用通用的專業模特兒描述

## 使用方式

### API 請求範例

```json
{
  "user_input": "休閒時尚穿搭",
  "selected_items": [
    {
      "id": "fc4b06d8-59d2-4ab9-82d3-8df145d86dbc",
      "name": "白色T恤",
      "category": "上衣",
      "img": null
    },
    {
      "id": "abb7e357-b620-4813-8360-1e60d82a46ff",
      "name": "牛仔褲",
      "category": "褲子",
      "img": null
    }
  ],
  "user_photo": null
}
```

### 測試腳本

使用 `test_virtual_fitting_uuid.py` 測試新的 API：

```bash
python test_virtual_fitting_uuid.py
```

## 前端整合建議

前端不再需要：
- ❌ 身高輸入欄位
- ❌ 體重輸入欄位
- ❌ 身體數據表單

前端只需要：
- ✅ 衣物選擇（支援 UUID）
- ✅ 風格描述輸入
- ✅ 照片上傳（可選）

## 優點

1. **更簡單的使用體驗** - 不需要輸入身體數據
2. **更快的流程** - 減少用戶輸入步驟
3. **更好的隱私保護** - 不收集敏感的身體數據
4. **支援 UUID** - 與現有資料庫結構相容

## 相關檔案

- `app/api/v1/virtual_fitting.py` - API 端點
- `app/services/image_generation.py` - 圖片生成服務
- `test_virtual_fitting_uuid.py` - 測試腳本
- `docs/VIRTUAL_FITTING_SETUP.md` - 完整設定指南
