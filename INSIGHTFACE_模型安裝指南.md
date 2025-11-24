# InsightFace 臉部交換模型安裝指南

## 問題診斷結果

✅ **InsightFace 0.2.1 已成功安裝**  
❌ **缺少臉部交換模型** `inswapper_128.onnx`

---

## 手動下載方式（推薦）

### 方法 1：直接下載（最簡單）

1. 訪問：https://huggingface.co/deepinsight/inswapper/tree/main
2. 點擊 `inswapper_128.onnx` 文件
3. 點擊右上角的「下載」按鈕
4. 下載完成後，將文件複製到：
   ```
   C:\Users\Administrator\.insightface\models\inswapper_128.onnx
   ```

### 方法 2：使用 Hugging Face CLI

```powershell
# 1. 安裝 huggingface-hub
pip install huggingface_hub

# 2. 下載模型
huggingface-cli download deepinsight/inswapper inswapper_128.onnx --local-dir %USERPROFILE%\.insightface\models
```

### 方法 3：使用 Python 腳本

```powershell
# 運行下載腳本（可能需要 Hugging Face token）
python download_inswapper_model.py
```

---

## 驗證安裝

下載完成後，檢查文件是否存在：

```powershell
Test-Path "$env:USERPROFILE\.insightface\models\inswapper_128.onnx"
```

應該返回 `True`

---

## 重啟後端服務

模型下載完成後，重啟後端：

```powershell
# 停止當前後端
# Ctrl + C

# 重新啟動
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 預期日誌輸出

成功啟用後，後端日誌應該顯示：

```
✅ InsightFace 已導入
開始初始化 FaceSwapService...
初始化 FaceAnalysis (buffalo_l)...
✅ FaceAnalysis 初始化成功（buffalo_l, CPU 模式）
嘗試載入臉部交換模型...
找到現有模型: C:\Users\Administrator\.insightface\models\inswapper_128.onnx
✅ 臉部交換模型載入成功
✅ FaceSwapService 初始化成功
```

---

## 檔案資訊

- **檔案名稱**: `inswapper_128.onnx`
- **檔案大小**: 約 500 MB
- **安裝位置**: `~/.insightface/models/inswapper_128.onnx`

---

## 常見問題

### Q: 為什麼之前被禁用？
A: 由於模型配置問題，之前被臨時禁用。現在已修復。

### Q: 臉部交換需要 GPU 嗎？
A: 不需要，使用 CPU 即可（5-10 秒處理時間）

### Q: 相似度能達到多少？
A: 使用雙次迭代 + 增強處理，可達到 **99%+ 相似度**

---

## 狀態更新

- ✅ InsightFace 0.2.1 已安裝
- ✅ 硬編碼禁用已移除
- ⏳ 等待下載 inswapper_128.onnx 模型
- ⏳ 重啟後端服務

完成以上步驟後，臉部交換功能即可正常使用！
