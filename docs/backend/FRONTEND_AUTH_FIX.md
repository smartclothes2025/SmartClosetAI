# 前端認證問題修復

修復時間: 2025-10-29 14:10

## 問題診斷 🔍

### 錯誤訊息
```
GET /api/v1/recommendations/inactive?days=90 
Status: 401 (Unauthorized)
Error: {"detail":"未提供 Authorization Bearer"}
```

### 根本原因
1. **後端需要認證**: `/api/v1/recommendations/inactive` 端點需要 Bearer Token 認證
2. **前端未發送 token**: `fetchJSON` 函數沒有自動帶上 Authorization header
3. **訪客 token 格式錯誤**: 訪客登入使用的 token 格式（`guest-token-000`）不符合後端期望的格式（`user-{uuid}-token`）

## 修復內容 ✅

### 1. 修改 fetchJSON 自動帶上 token

**檔案**: `src/lib/api.js`

**修改前**:
```javascript
const res = await fetch(url, opts);
```

**修改後**:
```javascript
// 自動從 localStorage 讀取 token 並加入 Authorization header
const token = localStorage.getItem('token');
const headers = {
  'Content-Type': 'application/json',
  ...opts.headers,
};

if (token) {
  headers['Authorization'] = `Bearer ${token}`;
  console.log('  🔑 Added Authorization header with token');
}

const res = await fetch(url, {
  ...opts,
  headers,
});
```

### 2. 修正訪客登入 token 格式

**檔案**: `src/pages/Login.jsx`

**修改前**:
```javascript
const fake = {
  token: 'guest-token-000',
  user: { id: 99, name: '訪客', email: 'guest@local', role: 'user' },
};
```

**修改後**:
```javascript
// 使用真實的測試使用者 ID
const testUserId = '9c33c7e9-ce22-4c4d-b385-15504ef368da';
const fake = {
  token: `user-${testUserId}-token`,
  user: { id: testUserId, name: '測試使用者', email: 'test@local', role: 'user' },
};
```

## 技術細節 🔧

### Token 流程

1. **登入時儲存 token**:
```javascript
localStorage.setItem('token', data.token);
```

2. **API 呼叫時自動帶上 token**:
```javascript
// 在 fetchJSON 中
const token = localStorage.getItem('token');
headers['Authorization'] = `Bearer ${token}`;
```

3. **後端驗證 token**:
```python
# 在 current_user_from_header 中
token = credentials.credentials
# 解析 user-{uuid}-token 格式
user_id = token[len("user-"):-len("-token")]
user = db.query(User).filter(User.id == user_id).first()
```

### Token 格式

**正確格式**: `user-{uuid}-token`

**範例**:
```
user-9c33c7e9-ce22-4c4d-b385-15504ef368da-token
```

**組成部分**:
- 前綴: `user-`
- UUID: 使用者的唯一識別碼
- 後綴: `-token`

## 測試驗證 ✅

### 測試步驟

1. **清除舊的 localStorage**:
```javascript
localStorage.clear();
```

2. **重新登入**（訪客登入）
   - 會儲存新的 token 格式

3. **訪問推薦頁面**
   - 應該可以正常顯示推薦內容

4. **檢查 Console**:
```
🔍 fetchJSON Debug:
  URL: /api/v1/recommendations/inactive?days=90
  ✅ Using REAL API via proxy
  🔑 Added Authorization header with token
  Response status: 200
  ✅ Success, data length: 1
```

### 預期結果

- ✅ 不再出現 401 錯誤
- ✅ 可以正常取得推薦資料
- ✅ Console 顯示已加入 Authorization header

## 影響範圍 📊

### 受益的 API 端點

所有需要認證的端點現在都會自動帶上 token：

1. **推薦相關**:
   - `/api/v1/recommendations/daily`
   - `/api/v1/recommendations/inactive`

2. **衣櫃相關**:
   - `/api/v1/clothes/` (GET, POST, DELETE)
   - `/api/v1/wardrobe/*`

3. **穿搭相關**:
   - `/api/v1/outfits/*`

4. **使用者相關**:
   - `/api/v1/profile/*`
   - `/api/v1/settings/*`

### 不受影響的端點

公開端點（不需要認證）：
- 登入: `/api/v1/auth/login`
- 註冊: `/api/v1/auth/register`
- 健康檢查: `/api/v1/ping-db`

## 安全性考量 🔐

### 1. Token 儲存

- ✅ 使用 localStorage（前端常見做法）
- ⚠️ 注意：localStorage 可能受到 XSS 攻擊
- 💡 建議：生產環境考慮使用 HttpOnly Cookie

### 2. Token 格式

- ✅ 簡單易懂（開發環境適用）
- ⚠️ 不夠安全（生產環境不建議）
- 💡 建議：生產環境使用 JWT

### 3. Token 過期

- ⚠️ 目前沒有過期機制
- 💡 建議：實作 token 刷新機制

## 後續改進建議 🚀

### 1. 實作正式的 JWT

**後端** (`app/api/v1/auth.py`):
```python
from jose import jwt
from datetime import datetime, timedelta

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "sub": user_id,
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**前端**:
```javascript
// Token 會自動過期，需要刷新
```

### 2. 實作 Token 刷新機制

```javascript
// 檢查 token 是否即將過期
function shouldRefreshToken(token) {
  const decoded = jwt_decode(token);
  const expiresIn = decoded.exp * 1000 - Date.now();
  return expiresIn < 5 * 60 * 1000; // 剩餘不到 5 分鐘
}

// 自動刷新
if (shouldRefreshToken(token)) {
  token = await refreshToken();
  localStorage.setItem('token', token);
}
```

### 3. 錯誤處理增強

```javascript
// 在 fetchJSON 中
if (res.status === 401) {
  // Token 無效或過期，重新導向到登入頁
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = '/login';
  throw new Error('認證過期，請重新登入');
}
```

### 4. 使用 Axios Interceptor

考慮使用 Axios 來簡化認證邏輯：

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1'
});

// 請求攔截器：自動加入 token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 響應攔截器：處理 401
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.clear();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

## 測試 Checklist ✓

- [x] 修改 `fetchJSON` 自動帶上 token
- [x] 修正訪客登入 token 格式
- [x] 確認 `/inactive` 端點可正常訪問
- [x] 確認 Console 顯示正確的 debug 訊息
- [x] 確認使用者隔離正常運作

## 相關檔案 📁

### 前端
- `src/lib/api.js` - API 呼叫工具（已修改）
- `src/pages/Login.jsx` - 登入頁面（已修改）
- `src/components/RecommendInactive.jsx` - 推薦組件（使用 fetchJSON）

### 後端
- `app/api/v1/recommendations.py` - 推薦 API（需要認證）
- `app/api/v1/auth.py` - 認證邏輯

### 文檔
- `FRONTEND_AUTH_FIX.md` - 本文檔
- `RECOMMENDATIONS_FEATURE_SUMMARY.md` - 推薦功能文檔

---

## 使用說明 💡

### 開發者測試

1. **清除舊資料**:
```javascript
// 在瀏覽器 Console 執行
localStorage.clear();
location.reload();
```

2. **重新登入**（訪客登入）

3. **檢查 Console**:
   - 應該看到 `🔑 Added Authorization header with token`
   - API 回應應該是 200

4. **檢查推薦功能**:
   - 應該能看到推薦的衣物
   - 不應該有 401 錯誤

### 前端整合

所有使用 `fetchJSON` 的地方都會自動帶上 token，無需修改：

```javascript
import fetchJSON from '../lib/api';

// 會自動加上 Authorization header
const data = await fetchJSON('/api/v1/recommendations/daily');
```

---

**狀態**: ✅ 完成並測試通過  
**影響範圍**: 所有 API 呼叫  
**測試使用者**: 9c33c7e9-ce22-4c4d-b385-15504ef368da
