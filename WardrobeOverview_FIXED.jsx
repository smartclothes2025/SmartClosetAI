import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import WardrobeItem from "./WardrobeItem";
import AskModal from "../AskModal";
import { useToast } from "../ToastProvider";

const filters = ["All", "tops", "pants", "skirts", "dresses", "outerwear", "shoes", "hats", "bags", "accessories", "socks"];
const API_BASE = (import.meta?.env?.VITE_API_BASE) || "";

// 輔助函式：取得 JWT Token
function getToken() {
  return localStorage.getItem("token") || "";
}

// ✅ 檢查是否為訪客帳號
function isGuestAccount() {
  const token = getToken();
  if (token === 'guest-token-000') return true;
  
  try {
    const userStr = localStorage.getItem('user');
    if (!userStr) return false;
    const user = JSON.parse(userStr);
    return user?.id === 99 || user?.name === '訪客' || user?.email === 'guest@local';
  } catch {
    return false;
  }
}

export default function WardrobeOverview() {
  const INACTIVE_THRESHOLD = 90;
  const { addToast } = useToast();

  // ✅ 清理啟動時的測試數據
  useEffect(() => {
    try {
      localStorage.removeItem("wardrobe_items");
      localStorage.removeItem("wardrobe_items_seed");
    } catch { }
  }, []);

  const [items, setItems] = useState([]);
  const [activeFilter, setActiveFilter] = useState(filters[0]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const navigate = useNavigate();

  // Modal 狀態
  const [askOpen, setAskOpen] = useState(false);
  const [askTargetId, setAskTargetId] = useState(null);
  const [batchAskOpen, setBatchAskOpen] = useState(false);

  // --- 數據載入邏輯 ---
  const fetchWardrobe = useCallback(async (signal) => {
    setLoading(true);
    setError("");
    
    // 訪客帳號檢查
    if (isGuestAccount()) {
      setItems([]);
      setError('訪客無法查看衣櫃，請用註冊帳號或其他使用者登入');
      setLoading(false);
      return;
    }

    const token = getToken();
    const headers = { Authorization: `Bearer ${token}` };
    
    // ✅ 統一且確定的 API 路由
    const URL = `${API_BASE}/api/v1/clothes`;
    
    try {
      const res = await fetch(URL, { method: "GET", headers, signal });
      
      if (res.status === 404) {
        throw new Error(`獲取衣物清單失敗: 後端路由 ${URL} 找不到 (404)`);
      }
      
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        console.error('[wardrobe] fetch failed', res.status, txt);
        throw new Error(`獲取衣物清單失敗: ${res.statusText}`);
      }
      
      const data = await res.json();
      
      // ✅ 處理不同的回傳格式
      const arr = Array.isArray(data) ? data : (Array.isArray(data?.initialItems) ? data.initialItems : null);
      if (!arr) {
        throw new Error("API 回傳格式非預期（請檢查後端是否回傳陣列或 { initialItems: [...] }）");
      }

      // ✅ 映射資料格式
      const mapped = arr.map((it) => {
        const img = it.img || "";
        return {
          id: Number.isInteger(+it.id) ? +it.id : it.id,
          name: it.name || "",
          category: it.category || "",
          wearCount: it.wearCount || 0,
          img: img || '/default-placeholder.png',
          daysInactive: typeof it.daysInactive === "number" ? it.daysInactive : null,
          color: it.color || "",
        };
      });

      setItems(mapped);

    } catch (err) {
      if (err?.name === "AbortError") return;
      console.warn("載入衣櫃失敗:", err);
      setError(err.message || "無法載入衣櫃，請確認後端或網路連線");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchWardrobe(controller.signal);
    return () => controller.abort();
  }, [fetchWardrobe]);

  // --- 刪除單一衣物 ---
  const deleteItem = useCallback(async (itemId) => {
    const token = getToken();
    const headers = { Authorization: `Bearer ${token}` };

    try {
      // ✅ 呼叫後端 DELETE 路由
      const res = await fetch(`${API_BASE}/api/v1/clothes/${itemId}`, {
        method: "DELETE",
        headers,
      });

      if (res.status === 204) {
        // ✅ 204 No Content 是成功的回應
        addToast({ type: 'success', title: '刪除成功', message: '該衣物已從衣櫃中移除。' });
        // ✅ 從本地狀態中移除
        setItems(prev => prev.filter(item => item.id !== itemId));
        return true;
      } else if (res.status === 403) {
        addToast({ type: 'error', title: '權限不足', message: '您沒有權限刪除這件衣物。' });
        return false;
      } else if (res.status === 404) {
        addToast({ type: 'warning', title: '找不到衣物', message: '該衣物可能已被刪除。' });
        // 仍然從本地移除
        setItems(prev => prev.filter(item => item.id !== itemId));
        return true;
      } else {
        const txt = await res.text().catch(() => "未知錯誤");
        addToast({ type: 'error', title: '刪除失敗', message: `後端錯誤：${res.status} ${txt}` });
        return false;
      }

    } catch (error) {
      console.error("刪除錯誤:", error);
      addToast({ type: 'error', title: '網路錯誤', message: '無法連線到伺服器，刪除失敗。' });
      return false;
    }
  }, [addToast]);

  // --- Modal 操作 ---
  function openAskModal(id) {
    setAskTargetId(id);
    setAskOpen(true);
  }

  function openBatchAskModal() {
    setBatchAskOpen(true);
  }

  // ✅ 批次刪除優化：使用 Promise.all 加速
  async function handleConfirmBatchDelete() {
    setBatchAskOpen(false);
    setLoading(true);
    
    try {
      // 並行刪除所有選取的項目
      const deletePromises = selectedIds.map(id => deleteItem(id));
      const results = await Promise.all(deletePromises);
      
      // 統計成功數量
      const successCount = results.filter(Boolean).length;
      
      if (successCount === selectedIds.length) {
        addToast({ 
          type: 'success', 
          title: '批次刪除完成', 
          message: `成功刪除 ${successCount} 件衣物` 
        });
      } else if (successCount > 0) {
        addToast({ 
          type: 'warning', 
          title: '部分刪除成功', 
          message: `成功刪除 ${successCount}/${selectedIds.length} 件衣物` 
        });
      }
    } catch (error) {
      console.error("批次刪除錯誤:", error);
      addToast({ type: 'error', title: '批次刪除失敗', message: '操作過程中發生錯誤' });
    } finally {
      setSelecting(false);
      setSelectedIds([]);
      setLoading(false);
    }
  }

  // --- 確認單一刪除 ---
  async function handleConfirmDelete() {
    if (!askTargetId) return;
    
    setAskOpen(false);
    setLoading(true);
    
    await deleteItem(askTargetId);
    
    setAskTargetId(null);
    setLoading(false);
  }

  // --- 篩選與選取邏輯 ---
  const filteredItems = items.filter((it) => activeFilter === "All" || it.category === activeFilter);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const goToVirtualFitting = () => {
    if (selectedIds.length === 0) return;
    const selectedItems = items.filter(item => selectedIds.includes(item.id));
    localStorage.setItem('virtual_fitting_items', JSON.stringify(selectedItems));
    navigate('/virtual-fitting');
  };

  return (
    <div>
      {/* 篩選按鈕 */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setActiveFilter(f)}
            className={`px-3 py-1 text-sm rounded-full transition-colors ${
              activeFilter === f 
                ? "bg-indigo-600 text-white" 
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            {f}
          </button>
        ))}

        {/* 操作按鈕 */}
        <div className="ml-auto flex items-center gap-2">
          {!selecting ? (
            <>
              <button 
                onClick={() => setSelecting(true)} 
                className="px-3 py-1 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
              >
                選取衣服
              </button>
              <button 
                onClick={() => navigate('/upload/select')} 
                className="px-3 py-1 text-sm rounded-md bg-gray-600 text-white hover:bg-gray-700 transition-colors"
              >
                新增衣物
              </button>
            </>
          ) : (
            <>
              {selectedIds.length > 0 && (
                <button
                  onClick={openBatchAskModal}
                  className="px-3 py-1 text-sm rounded-md bg-red-600 text-white hover:bg-red-700 transition-colors"
                >
                  刪除（{selectedIds.length}）
                </button>
              )}
              
              <button
                onClick={goToVirtualFitting}
                disabled={selectedIds.length === 0}
                className="px-3 py-1 text-sm rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                虛擬試衣（{selectedIds.length}）
              </button>
              
              <button
                onClick={() => {
                  setSelecting(false);
                  setSelectedIds([]);
                }}
                className="px-3 py-1 text-sm rounded-md bg-gray-200 hover:bg-gray-300 transition-colors"
              >
                取消
              </button>
            </>
          )}
        </div>
      </div>

      {/* 載入與錯誤狀態 */}
      {loading && <div className="py-6 text-gray-500">載入中…</div>}
      {error && <div className="py-2 text-red-600">{error}</div>}

      {/* 空資料提示 */}
      {!loading && !error && filteredItems.length === 0 && (
        <div className="text-gray-500 text-center py-8">
          目前衣櫃沒有衣服<br />
          請先確認是否有上傳衣服
        </div>
      )}

      {/* 衣物列表 */}
      {!loading && filteredItems.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {filteredItems.map((item) => (
            <WardrobeItem
              key={item.id}
              item={item}
              selecting={selecting}
              active={selectedIds.includes(item.id)}
              onToggle={() => toggleSelect(item.id)}
              onDelete={() => openAskModal(item.id)}
              inactiveThreshold={INACTIVE_THRESHOLD}
            />
          ))}
        </div>
      )}

      {/* 單一刪除確認 Modal */}
      <AskModal
        open={askOpen}
        title="刪除衣物"
        message="確定要刪除此衣物？"
        confirmText="刪除"
        cancelText="取消"
        destructive={true}
        onCancel={() => { 
          setAskOpen(false); 
          setAskTargetId(null); 
        }}
        onConfirm={handleConfirmDelete}
      />

      {/* 批次刪除確認 Modal */}
      <AskModal
        open={batchAskOpen}
        title="刪除多筆衣物"
        message={`確定要刪除選中的 ${selectedIds.length} 件衣物嗎？`}
        confirmText="刪除"
        cancelText="取消"
        destructive={true}
        onCancel={() => setBatchAskOpen(false)}
        onConfirm={handleConfirmBatchDelete}
      />
    </div>
  );
}
