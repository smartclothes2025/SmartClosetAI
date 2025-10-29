import React from "react";

/**
 * WardrobeItem - 衣櫃單品卡片組件
 * 
 * @param {Object} item - 衣物項目資料
 * @param {boolean} selecting - 是否處於選取模式
 * @param {boolean} active - 是否被選中
 * @param {Function} onToggle - 選取切換回調
 * @param {number} inactiveThreshold - 未穿天數警告閾值
 * @param {Function} onDelete - 刪除回調（父組件已綁定 item.id）
 */
export default function WardrobeItem({
  item,
  selecting = false,
  active = false,
  onToggle = () => {},
  inactiveThreshold = 90,
  onDelete = () => {}, // ✅ 父組件通過閉包已綁定特定 item，直接呼叫即可
}) {
  const name = item?.name ?? "未命名";
  const category = item?.category ?? "";
  const color = item?.color ?? "";
  const img = item?.img ?? "";
  const daysInactive = typeof item?.daysInactive === 'number' ? item.daysInactive : null;
  const ownerId = item?.ownerId ?? null; // ✅ 從 item 中取得 ownerId

  // ✅ 處理卡片點擊（僅在選取模式下）
  const handleCardClick = () => {
    if (selecting) {
      onToggle();
    }
  };

  // ✅ 處理刪除按鈕點擊
  const handleDeleteClick = (e) => {
    e.stopPropagation(); // 防止觸發卡片點擊
    onDelete(); // ✅ 修正：直接呼叫 onDelete()，不傳參數（父組件已綁定）
  };

  return (
    <div
      className={`relative border rounded-xl p-3 bg-white shadow-sm transition-transform hover:scale-[1.01] ${
        selecting && active ? 'ring-2 ring-indigo-500' : ''
      } ${selecting ? 'cursor-pointer' : ''}`}
      onClick={handleCardClick}
    >
      {/* ✅ 刪除按鈕（僅在非選取模式時顯示） */}
      {!selecting && (
        <button
          onClick={handleDeleteClick}
          className="absolute top-2 left-2 w-6 h-6 flex items-center justify-center text-gray-600 bg-white border border-gray-300 rounded-full hover:bg-red-50 hover:text-red-600 hover:border-red-300 shadow-sm text-sm font-bold transition-colors z-10"
          title="刪除此衣物"
          aria-label={`刪除 ${name}`}
        >
          ✕
        </button>
      )}

      {/* ✅ 未穿天數警告徽章 */}
      {daysInactive !== null && daysInactive >= inactiveThreshold && (
        <div className="absolute top-2 right-2 z-10">
          <span className="text-xs bg-amber-500 text-white px-2 py-0.5 rounded-full shadow">
            已 {daysInactive} 天未穿
          </span>
        </div>
      )}

      {/* ✅ 選取模式的勾選標記 */}
      {selecting && (
        <div
          className={`absolute top-2 left-2 w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs select-none transition-all z-10
            ${active ? 'bg-indigo-600 border-indigo-600 text-white scale-110' : 'bg-white border-gray-300 text-transparent'}`}
          aria-hidden="true"
        >
          ✓
        </div>
      )}

      {/* ✅ 衣物圖片區域 */}
      <div className="aspect-square w-full overflow-hidden rounded-lg flex items-center justify-center bg-gray-50">
        {img ? (
          <img 
            src={img} 
            alt={name} 
            className="max-w-full max-h-full object-contain"
            loading="lazy"
            onError={(e) => {
              // ✅ 圖片載入失敗時顯示預設圖示
              e.target.style.display = 'none';
              e.target.parentElement.innerHTML = '<div class="text-4xl">👚</div>';
            }}
          />
        ) : (
          <div className="text-4xl">👚</div>
        )}
      </div>

      {/* ✅ 衣物資訊 */}
      <div className="mt-2 text-sm">
        <div className="font-medium truncate" title={name}>
          {name}
        </div>
        <div className="text-gray-500 truncate" title={`${category}${category && color ? ' • ' : ''}${color}`}>
          {category}
          {category && color ? ' • ' : ''}
          {color}
        </div>
        {ownerId != null && (
          <div className="text-xs text-gray-400 truncate mt-1" title={`擁有者 ID: ${ownerId}`}>
            擁有者: {ownerId}
          </div>
        )}
      </div>
    </div>
  );
}
