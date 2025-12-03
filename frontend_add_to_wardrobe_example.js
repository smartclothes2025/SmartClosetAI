/**
 * 品牌合作商品加入衣櫥功能
 * 
 * 使用方式：
 * 1. 在購買按鈕的 onClick 事件中調用 handlePurchaseAndAddToWardrobe
 * 2. 會同時開啟外部購買連結並將商品加入衣櫥
 */

/**
 * 將店家商品加入用戶衣櫥
 * @param {number} productId - 商品 ID
 * @param {string} token - 用戶認證 token
 * @returns {Promise<Object>} API 回應
 */
async function addStoreItemToWardrobe(productId, token) {
  const API_BASE_URL = 'http://localhost:8000'; // 根據環境調整
  
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/store/items/${productId}/add-to-wardrobe`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || '加入衣櫥失敗');
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('加入衣櫥失敗:', error);
    throw error;
  }
}

/**
 * 處理購買按鈕點擊：同時跳轉外部連結並加入衣櫥
 * @param {number} productId - 商品 ID
 * @param {string} purchaseUrl - 外部購買連結
 * @param {string} token - 用戶認證 token
 */
async function handlePurchaseAndAddToWardrobe(productId, purchaseUrl, token) {
  try {
    // 1. 立即開啟外部購買連結（不等待 API）
    window.open(purchaseUrl, '_blank');
    
    // 2. 同時調用加入衣櫥 API
    const result = await addStoreItemToWardrobe(productId, token);
    
    // 3. 顯示成功訊息
    if (result.item.already_exists) {
      console.log('此商品已在您的衣櫥中');
      // 可選：顯示 toast 通知
      showToast('此商品已在您的衣櫥中', 'info');
    } else {
      console.log('成功加入衣櫥:', result.item.name);
      // 可選：顯示 toast 通知
      showToast(`${result.item.name} 已加入衣櫥`, 'success');
    }
    
    return result;
  } catch (error) {
    console.error('處理失敗:', error);
    // 可選：顯示錯誤訊息
    showToast('加入衣櫥失敗，請稍後再試', 'error');
    throw error;
  }
}

/**
 * Toast 通知函數（需要根據實際使用的 UI 框架調整）
 */
function showToast(message, type = 'info') {
  // 使用 alert 作為簡單示範，實際應使用 toast 組件
  console.log(`[${type.toUpperCase()}] ${message}`);
  
  // 如果使用 React + react-toastify:
  // import { toast } from 'react-toastify';
  // toast[type](message);
  
  // 如果使用原生 JavaScript，可以建立簡單的 toast 元素
  const toastEl = document.createElement('div');
  toastEl.className = `toast toast-${type}`;
  toastEl.textContent = message;
  toastEl.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 24px;
    background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
    color: white;
    border-radius: 8px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    z-index: 9999;
    animation: slideIn 0.3s ease-out;
  `;
  
  document.body.appendChild(toastEl);
  
  setTimeout(() => {
    toastEl.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => toastEl.remove(), 300);
  }, 3000);
}

// ============================================
// React 組件範例
// ============================================

/**
 * React 組件中的使用範例
 */
function StoreItemCard({ item, token }) {
  const handlePurchaseClick = async () => {
    try {
      await handlePurchaseAndAddToWardrobe(
        item.id,
        item.purchaseUrl,
        token
      );
    } catch (error) {
      // 錯誤已在 handlePurchaseAndAddToWardrobe 中處理
    }
  };
  
  return (
    <div className="store-item-card">
      <img src={item.imageUrl} alt={item.name} />
      <h3>{item.name}</h3>
      <p>{item.category}</p>
      
      <button 
        onClick={handlePurchaseClick}
        className="purchase-button"
      >
        購買並加入衣櫥
      </button>
    </div>
  );
}

// ============================================
// 原生 JavaScript 範例
// ============================================

/**
 * 原生 JavaScript 中的使用範例
 */
document.addEventListener('DOMContentLoaded', () => {
  // 假設有多個購買按鈕，每個都有 data-product-id 和 data-purchase-url
  const purchaseButtons = document.querySelectorAll('.purchase-button');
  
  purchaseButtons.forEach(button => {
    button.addEventListener('click', async (e) => {
      e.preventDefault();
      
      const productId = parseInt(button.dataset.productId);
      const purchaseUrl = button.dataset.purchaseUrl;
      const token = localStorage.getItem('authToken'); // 從 localStorage 取得 token
      
      if (!token) {
        alert('請先登入');
        return;
      }
      
      try {
        await handlePurchaseAndAddToWardrobe(productId, purchaseUrl, token);
      } catch (error) {
        // 錯誤已處理
      }
    });
  });
});

// ============================================
// HTML 範例
// ============================================

/**
 * HTML 標記範例：
 * 
 * <div class="store-item">
 *   <img src="https://..." alt="商品名稱">
 *   <h3>女生灰T恤（通勤）</h3>
 *   <button 
 *     class="purchase-button"
 *     data-product-id="1"
 *     data-purchase-url="https://styleshop-delta.vercel.app/product-detail.html?id=1"
 *   >
 *     購買並加入衣櫥
 *   </button>
 * </div>
 */

// ============================================
// API 回應格式
// ============================================

/**
 * 成功回應範例（新增）：
 * {
 *   "message": "成功加入衣櫥",
 *   "item": {
 *     "id": "123",
 *     "name": "女生灰T恤（通勤）",
 *     "category": "上衣",
 *     "color": "neutral",
 *     "img": "gs://smartclothes_wardrobe/wardrobe/1/tops/store_1.jpg",
 *     "source": "store",
 *     "product_id": 1,
 *     "already_exists": false
 *   }
 * }
 * 
 * 成功回應範例（已存在）：
 * {
 *   "message": "此商品已在您的衣櫥中",
 *   "item": {
 *     "id": "123",
 *     "name": "女生灰T恤（通勤）",
 *     "category": "上衣",
 *     "color": "neutral",
 *     "img": "gs://smartclothes_wardrobe/wardrobe/1/tops/store_1.jpg",
 *     "source": "store",
 *     "already_exists": true
 *   }
 * }
 * 
 * 錯誤回應範例：
 * {
 *   "detail": "找不到商品 ID: 999"
 * }
 */

export { 
  addStoreItemToWardrobe, 
  handlePurchaseAndAddToWardrobe,
  showToast 
};
