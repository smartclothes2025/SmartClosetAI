# 虛擬試衣 vs 小助手 - 對比分析

## 關鍵差異

### 1. 頭貼下載邏輯

**虛擬試衣（virtual_fitting.py）**:
```python
if current_user.picture.startswith("gs://"):
    user_photo_base64 = await image_service.download_user_photo_from_gcs(
        current_user.picture,    # 參數 1：picture_uri
        str(current_user.id)     # 參數 2：user_id
    )
```

**小助手（fashion_advisor.py）**:
```python
full_gcs_uri = user_picture_uri
if not user_picture_uri.startswith("gs://"):
    full_gcs_uri = f"gs://{self.user_photo_bucket_name}/{user_id}/{user_picture_uri.lstrip('/')}"

user_photo_base64 = await img_gen_service.download_user_photo_from_gcs(
    picture_uri=full_gcs_uri,  # 使用關鍵字參數
    user_id=user_id
)
```

### 2. 可能的問題

#### 問題 1：頭貼 URI 格式不一致
- 虛擬試衣：假設 `current_user.picture` 已經是完整的 `gs://` URI
- 小助手：嘗試自動構建完整 URI

#### 問題 2：user_photo_bucket_name 可能錯誤
- 檢查 `self.user_photo_bucket_name` 是否正確設置

#### 問題 3：頭貼下載返回 None
- 可能是權限問題
- 可能是路徑錯誤
- 可能是文件不存在

## 測試步驟

### 步驟 1：檢查後端日誌

當你在小助手輸入「穿搭」時，檢查日誌中是否有：

```
✅ 優先級 2: 沒有上傳照片，準備下載用戶頭貼
    原始 URI: 'xxx'
    🔧 自動構建完整 GCS URI: gs://smartclothes_userphoto/1/xxx
🔄 開始下載用戶頭貼...
✅ 成功下載並使用用戶頭貼！
    Base64 長度: xxx chars
```

### 步驟 2：如果看到下載失敗

```
❌ 用戶頭貼下載返回 None！
    URI: gs://smartclothes_userphoto/1/xxx
```

這表示：
1. GCS 中不存在此文件
2. 路徑錯誤
3. 權限問題

### 步驟 3：如果頭貼下載成功，但圖片還是不像

這表示 Gemini 沒有使用你的照片，可能原因：
1. `user_photo_base64` 沒有正確傳遞給 `generate_tryon_image()`
2. Gemini 提示詞有問題
3. Gemini 本身的限制（只能 30-70% 相似）

## 快速修復方案

### 方案 1：強制使用虛擬試衣的邏輯

修改 `fashion_advisor.py`，使用與虛擬試衣完全相同的頭貼下載方式：

```python
# 不要自動構建 URI，直接使用原始 URI
if user_picture_uri:
    user_photo_base64 = await img_gen_service.download_user_photo_from_gcs(
        user_picture_uri,    # 直接傳，不修改
        str(user_id)
    )
```

### 方案 2：添加調試日誌

在調用 `generate_tryon_image()` 之前，添加：

```python
logger.info(f"🔍 調試資訊:")
logger.info(f"   user_photo_base64 是否存在: {bool(user_photo_base64)}")
if user_photo_base64:
    logger.info(f"   長度: {len(user_photo_base64)}")
    logger.info(f"   前 50 字元: {user_photo_base64[:50]}")
```

## 我的猜測

我猜測問題在於：

**頭貼下載成功了，但 Gemini 只能達到 30-70% 相似度。**

這不是 bug，而是 Gemini 的能力限制。虛擬試衣「100% 效果」可能是：
1. 你沒有上傳頭貼，所以用的是預設模特兒（效果一致）
2. 或者你上傳了照片，效果也是 30-70%，只是你覺得可以接受

**真正要達到 99%+ 相似度，必須使用臉部交換技術（InsightFace），但這個在你的環境中安裝失敗了。**
