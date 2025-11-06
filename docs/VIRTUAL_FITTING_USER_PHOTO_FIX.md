# 虛擬試衣用戶照片功能修復指南

## 問題描述
用戶上傳臉部照片後，系統沒有使用用戶的臉來生成穿搭圖，而是繼續使用陌生人（預設模特兒）。

## 已完成的後端修改

### 1. `app/services/image_generation.py`
- ✅ 修改 `generate_tryon_image` 方法，添加 `user_photo_base64` 參數
- ✅ 修改 `_generate_with_clothing_images` 方法，支援接收用戶照片
- ✅ 根據是否有用戶照片，生成不同的提示詞：
  - **有用戶照片**：要求 AI 使用用戶的臉部特徵生成穿搭圖
  - **無用戶照片**：使用亞洲（台灣）女性模特兒

### 2. `app/api/v1/virtual_fitting.py`
- ✅ 修改 `/generate` 端點，接收 `user_photo` 參數
- ✅ 處理 data URL 格式，提取 base64 數據
- ✅ 將用戶照片傳遞給圖片生成服務

## 需要修改的前端代碼

### 問題分析
前端 `VirtualFitting.jsx` 中的問題：
1. `autoGenerateImage` 在 `useEffect` 中被調用，此時 `userPhoto` 還是 `null`
2. 用戶上傳照片後，沒有觸發重新生成
3. 前端需要將 `userPhoto` 轉換為 base64 並傳遞給後端

### 修改方案

#### 方案 1：上傳照片後自動重新生成（推薦）

在 `handlePhotoUpload` 函數中，當用戶上傳照片後自動重新生成：

```jsx
// 處理用戶照片上傳
const handlePhotoUpload = (e) => {
  const file = e.target.files[0];
  if (file) {
    setUserPhoto(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setUserPhotoPreview(reader.result);
      // 上傳照片後自動重新生成（使用 base64 格式）
      autoGenerateImageWithPhoto(selectedItems, reader.result);
    };
    reader.readAsDataURL(file);
  }
};

// 新增：帶照片的生成函數
const autoGenerateImageWithPhoto = async (items, photoBase64) => {
  if (!items || items.length === 0) {
    return;
  }

  setGenerating(true);
  setGeneratedImageUrl(null);
  setGenerationError(null);

  try {
    const token = localStorage.getItem('token');
    
    const payload = {
      user_input: "根據我的照片和選中的衣物，生成一套適合我的時尚穿搭",
      selected_items: items.map(item => ({
        id: item.id,
        name: item.name,
        category: item.category
      })),
      user_photo: photoBase64  // 傳遞 base64 格式的照片
    };

    const res = await fetch(`${API_BASE}/fitting/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const result = await res.json();
      if (result.type === 'image' && result.url) {
        setGeneratedImageUrl(result.url);
        setUsedPrompt(result.prompt_used || '');
      } else {
        setGenerationError(result.text || '請配置 AI 圖片生成服務');
      }
    } else {
      const errorText = await res.text();
      setGenerationError(`生成失敗: ${errorText}`);
    }
  } catch (err) {
    console.error('生成圖片失敗:', err);
    setGenerationError(`錯誤: ${err.message}`);
  } finally {
    setGenerating(false);
  }
};
```

#### 方案 2：修改現有的 `autoGenerateImage` 函數

將 `autoGenerateImage` 修改為接收可選的照片參數：

```jsx
// 修改後的 autoGenerateImage
const autoGenerateImage = async (items, photoBase64 = null) => {
  if (!items || items.length === 0) {
    return;
  }

  setGenerating(true);
  setGeneratedImageUrl(null);
  setGenerationError(null);

  try {
    const token = localStorage.getItem('token');
    
    // 構建請求 payload
    const payload = {
      user_input: photoBase64 
        ? "根據我的照片和選中的衣物，生成一套適合我的時尚穿搭"
        : "專業時尚模特兒展示，高質感穿搭攝影，自然光線，簡約背景",
      selected_items: items.map(item => ({
        id: item.id,
        name: item.name,
        category: item.category
      }))
    };
    
    // 如果有用戶照片，添加到 payload
    if (photoBase64) {
      payload.user_photo = photoBase64;
    }

    const res = await fetch(`${API_BASE}/fitting/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const result = await res.json();
      if (result.type === 'image' && result.url) {
        setGeneratedImageUrl(result.url);
        setUsedPrompt(result.prompt_used || '');
      } else {
        setGenerationError(result.text || '請配置 AI 圖片生成服務');
      }
    } else {
      const errorText = await res.text();
      setGenerationError(`生成失敗: ${errorText}`);
    }
  } catch (err) {
    console.error('生成圖片失敗:', err);
    setGenerationError(`錯誤: ${err.message}`);
  } finally {
    setGenerating(false);
  }
};

// 修改 handlePhotoUpload
const handlePhotoUpload = (e) => {
  const file = e.target.files[0];
  if (file) {
    setUserPhoto(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setUserPhotoPreview(reader.result);
      // 上傳照片後自動重新生成
      autoGenerateImage(selectedItems, reader.result);
    };
    reader.readAsDataURL(file);
  }
};

// 修改 handleRegenerate
const handleRegenerate = () => {
  autoGenerateImage(selectedItems, userPhotoPreview);
};
```

#### 方案 3：添加「使用我的照片生成」按鈕

如果不想自動重新生成，可以添加一個按鈕：

```jsx
{/* 在照片上傳區域下方添加 */}
{userPhotoPreview && (
  <button
    onClick={() => autoGenerateImage(selectedItems, userPhotoPreview)}
    className="mt-2 w-full bg-pink-500 text-white px-4 py-2 rounded-lg hover:bg-pink-600 transition-colors"
  >
    🎨 使用我的照片重新生成
  </button>
)}
```

## 推薦實施方案

**推薦使用方案 2**，因為：
1. 修改最少，邏輯清晰
2. 上傳照片後自動重新生成，用戶體驗好
3. 重新生成按鈕也能正確使用用戶照片

## 測試步驟

1. 啟動後端服務
2. 打開虛擬試衣頁面
3. 選擇衣物後，應該看到預設模特兒的穿搭圖
4. 上傳自己的臉部照片
5. 系統應該自動重新生成，這次使用用戶的臉部特徵
6. 點擊「重新生成」按鈕，應該繼續使用用戶的臉

## 預期效果

- **無用戶照片**：生成亞洲（台灣）女性模特兒穿著選中衣物的照片
- **有用戶照片**：生成用戶本人穿著選中衣物的照片，保持用戶的臉部特徵

## 注意事項

1. 用戶照片應該是清晰的臉部照片，正面效果最佳
2. 照片格式支援：JPG、PNG 等常見格式
3. 照片會被自動調整大小（最大 1024x1024）
4. AI 生成時間約 10-30 秒，請耐心等待
