# CategoryEnum 錯誤修復

## 🐛 問題描述

後端 API 出現錯誤：
```
AttributeError: type object 'CategoryEnum' has no attribute 'OUTERWEAR'
```

**錯誤位置**：`app/api/v1/store.py` 第 192 行

**錯誤原因**：
- `CategoryEnum` 定義中使用的是 `OUTER`（外套）
- 但 `store.py` 中錯誤使用了 `OUTERWEAR`

## ✅ 修復方案

### CategoryEnum 定義（正確）

**檔案**：`app/models/wardrobe.py` (第 9-19 行)

```python
class CategoryEnum(str, Enum):
    TOP = "上衣"
    SKIRT = "裙子"
    PANTS = "褲子"
    DRESS = "洋裝"
    OUTER = "外套"      # ✅ 正確：使用 OUTER
    SHOES = "鞋子"
    SOCKS = "襪子"
    HAT = "帽子"
    BAG = "包包"
    ACCESSORY = "配件"
```

### 修復 store.py

**檔案**：`app/api/v1/store.py` (第 187-198 行)

**修改前**：
```python
category_map = {
    "上衣": CategoryEnum.TOP,
    "褲子": CategoryEnum.PANTS,
    "裙子": CategoryEnum.SKIRT,
    "洋裝": CategoryEnum.DRESS,
    "外套": CategoryEnum.OUTERWEAR,  # ❌ 錯誤
    "鞋子": CategoryEnum.SHOES,
    "帽子": CategoryEnum.HAT,
    "包包": CategoryEnum.BAG,
    "配件": CategoryEnum.ACCESSORY,
    "下身": CategoryEnum.PANTS,
}
```

**修改後**：
```python
category_map = {
    "上衣": CategoryEnum.TOP,
    "褲子": CategoryEnum.PANTS,
    "裙子": CategoryEnum.SKIRT,
    "洋裝": CategoryEnum.DRESS,
    "外套": CategoryEnum.OUTER,  # ✅ 修復：改為 OUTER
    "鞋子": CategoryEnum.SHOES,
    "帽子": CategoryEnum.HAT,
    "包包": CategoryEnum.BAG,
    "配件": CategoryEnum.ACCESSORY,
    "下身": CategoryEnum.PANTS,
}
```

## 🔍 檢查其他檔案

已檢查以下檔案，確認沒有其他地方使用 `CategoryEnum.OUTERWEAR`：
- ✅ `app/api/v1/upload.py` - 使用字串 "outerwear"（正確）
- ✅ `app/api/v1/clothes.py` - 使用字串 "outerwear"（正確）
- ✅ `app/services/*.py` - 未使用 CategoryEnum

## 🧪 測試方式

### 1. 重啟後端服務

```powershell
# 停止現有服務
Ctrl+C

# 重新啟動
.\start_backend.bat
# 或
python start_server.py
```

### 2. 測試加入衣櫥功能

```bash
# 使用 curl 測試
curl -X POST \
  "https://cometical-kyphotic-deborah.ngrok-free.dev/api/v1/store/items/76/add-to-wardrobe" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. 前端測試

1. 進入「本日主打色」頁面
2. 點擊包包類商品（ID: 76）
3. 檢查：
   - ✅ 不再出現 500 錯誤
   - ✅ 商品成功加入衣櫥
   - ✅ 跳轉到衣櫥頁面
   - ✅ 開啟新分頁到外部購物網站

## 📊 錯誤日誌分析

**原始錯誤**：
```
INFO:app.api.v1.store:[add-to-wardrobe] 找到店家商品: 抽象印花腋下包（日常）
INFO:app.api.v1.store:[add-to-wardrobe] 下載圖片: https://storage.googleapis.com/...
ERROR:app.api.v1.store:[add-to-wardrobe] 加入衣櫥失敗
Traceback (most recent call last):
  File "...\store.py", line 192, in add_store_item_to_wardrobe
    "外套": CategoryEnum.OUTERWEAR,
            ^^^^^^^^^^^^^^^^^^^^^^
AttributeError: type object 'CategoryEnum' has no attribute 'OUTERWEAR'
```

**修復後應該看到**：
```
INFO:app.api.v1.store:[add-to-wardrobe] 找到店家商品: 抽象印花腋下包（日常）
INFO:app.api.v1.store:[add-to-wardrobe] 下載圖片: https://storage.googleapis.com/...
INFO:app.api.v1.store:[add-to-wardrobe] GCS 上傳成功: gs://...
INFO:app.api.v1.store:[add-to-wardrobe] 成功加入衣櫥: uuid
INFO:     200 OK
```

## 📝 CategoryEnum 完整對照表

| 中文 | Enum 值 | 英文 key | GCS 路徑 |
|------|---------|----------|----------|
| 上衣 | `CategoryEnum.TOP` | tops | tops |
| 褲子 | `CategoryEnum.PANTS` | pants | bottoms |
| 裙子 | `CategoryEnum.SKIRT` | skirts | skirts |
| 洋裝 | `CategoryEnum.DRESS` | dresses | dresses |
| 外套 | `CategoryEnum.OUTER` | outerwear | outerwear |
| 鞋子 | `CategoryEnum.SHOES` | shoes | shoes |
| 襪子 | `CategoryEnum.SOCKS` | socks | socks |
| 帽子 | `CategoryEnum.HAT` | hats | hats |
| 包包 | `CategoryEnum.BAG` | bags | bags |
| 配件 | `CategoryEnum.ACCESSORY` | accessories | accessories |

## 🎯 重點提醒

1. **Enum 屬性名稱**：使用 `OUTER` 而不是 `OUTERWEAR`
2. **字串映射**：可以使用 "outerwear"（如 GCS 路徑）
3. **一致性**：所有使用 `CategoryEnum` 的地方都要使用正確的屬性名稱

## 🔄 相關檔案

- **模型定義**：`app/models/wardrobe.py`
- **店家 API**：`app/api/v1/store.py`
- **上傳 API**：`app/api/v1/upload.py`
- **衣物 API**：`app/api/v1/clothes.py`

---

**修復日期**：2025-12-03  
**修復狀態**：✅ 已完成  
**需要重啟**：是（需要重啟後端服務）
