"""
店家商品服務
從 styleshop_images_config.json 讀取並提供篩選功能
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from functools import lru_cache
import os

logger = logging.getLogger(__name__)

# 色系映射表（根據檔名關鍵字）
# 中性：僅黑 / 白 / 灰；卡其、奶茶等暖色統一歸入 khaki
PALETTE_KEYWORDS = {
    "neutral": ["灰", "白", "黑"],
    "khaki": ["卡其", "棕", "咖", "奶茶"],
    "blue": ["藍", "深藍", "海軍藍", "淺藍"],
    "pink": ["粉", "紅粉", "紅", "正紅"],
    "green": ["綠", "軍綠", "橄欖綠", "淺綠"],
}

# 類別映射
CATEGORY_MAP = {
    "上衣": "上衣",
    "下身": "褲子",  # 統一處理下身
    "裙": "裙子",
    "洋裝": "洋裝",
    "外套": "外套",
    "包包": "包包",
    "配件": "配件",
}


class StoreItem:
    """店家商品資料結構"""
    def __init__(self, filename: str, url: str, gender: str, item_id: int = None):
        self.filename = filename
        self.url = url
        self.gender = gender
        self.item_id = item_id  # 唯一數字 ID
        self._parse_filename()
    
    def _parse_filename(self):
        """從檔名解析資訊"""
        # 例: "上衣/女生灰T恤（通勤）.png" -> category="上衣", name="女生灰T恤（通勤）"
        parts = self.filename.split("/")
        if len(parts) >= 2:
            self.category = parts[0]
            self.name = parts[1].replace(".png", "").replace(".JPG", "").replace(".jpg", "")
        else:
            self.category = "其他"
            self.name = self.filename
        
        # 推測色系
        self.palette = self._detect_palette()
    
    def _detect_palette(self) -> str:
        """從檔名推測色系"""
        name_lower = self.name.lower()
        for palette_key, keywords in PALETTE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in self.name:
                    return palette_key
        return "neutral"  # 預設中性
    
    def to_dict(self) -> Dict[str, Any]:
        """轉為字典"""
        product_id = self.item_id if self.item_id is not None else hash(self.filename) % 10000
        return {
            "id": product_id,  # 使用數字 ID
            "productId": product_id,  # 相容欄位
            "name": self.name,
            "category": self.category,
            "palette": self.palette,
            "imageUrl": self.url,
            "gender": self.gender,
            "source": "store",
            "purchaseUrl": f"https://styleshop-delta.vercel.app/product-detail.html?id={product_id}",
        }


class StoreItemService:
    """店家商品服務"""
    
    def __init__(self, config_path: Optional[Path] = None, id_mapping_path: Optional[Path] = None):
        if config_path is None:
            # 預設路徑
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "styleshop_images_config.json"
        else:
            base_dir = Path(config_path).parent

        # id 對應檔（用來對齊 women.js / man.js 的商品 id）
        if id_mapping_path is None:
            id_mapping_path = base_dir / "styleshop_id_mapping.json"

        self.config_path = Path(config_path)
        self.id_mapping_path = Path(id_mapping_path)
        self._id_mapping: Dict[str, Dict[str, int]] = self._load_id_mapping()

        self._items: List[StoreItem] = []
        self._load_items()

    def _load_id_mapping(self) -> Dict[str, Dict[str, int]]:
        """載入 gender + filename -> product id 的對應表。

        檔案格式示例：
        {
          "women": {"上衣/休閒黑色背心.png": 1},
          "men":   {"上衣/奶茶POLO（通勤）.png": 101}
        }
        """
        mapping: Dict[str, Dict[str, int]] = {}

        if not self.id_mapping_path.exists():
            return mapping

        try:
            with open(self.id_mapping_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            if not isinstance(raw, dict):
                return mapping

            for gender, m in raw.items():
                if not isinstance(m, dict):
                    continue
                gender_map: Dict[str, int] = {}
                for filename, pid in m.items():
                    try:
                        gender_map[str(filename)] = int(pid)
                    except (TypeError, ValueError):
                        continue
                if gender_map:
                    mapping[str(gender)] = gender_map

        except Exception as e:
            logger.error(f"載入 styleshop_id_mapping 失敗: {e}")

        return mapping
    
    def _load_items(self):
        """載入商品資料"""
        if not self.config_path.exists():
            logger.warning(f"找不到店家配置檔: {self.config_path}")
            return
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 解析 women 和 men
            item_id_counter = 1
            images = data.get("images", {}) or {}
            for gender in ["women", "men"]:
                gender_images = images.get(gender) or {}
                if not isinstance(gender_images, dict):
                    continue

                gender_mapping = self._id_mapping.get(gender, {})

                for filename, url in gender_images.items():
                    # 若 mapping 檔中有設定，優先使用對應的 product id
                    mapped_id = gender_mapping.get(filename)
                    if mapped_id is not None:
                        item_id = mapped_id
                    else:
                        item_id = item_id_counter
                        item_id_counter += 1

                    item = StoreItem(filename, url, gender, item_id=item_id)
                    self._items.append(item)
            
            logger.info(f"已載入 {len(self._items)} 件店家商品")
        
        except Exception as e:
            logger.error(f"載入店家配置失敗: {e}")
    
    def get_items(
        self,
        gender: Optional[Literal["women", "men"]] = None,
        palette: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        取得店家商品
        
        Args:
            gender: 性別篩選
            palette: 色系篩選
            category: 類別篩選
            limit: 限制數量
        """
        results = self._items
        
        # 性別篩選
        if gender:
            results = [item for item in results if item.gender == gender]
        
        # 色系篩選
        if palette:
            results = [item for item in results if item.palette == palette]
        
        # 類別篩選
        if category:
            results = [item for item in results if item.category == category]
        
        # 限制數量
        results = results[:limit]
        
        return [item.to_dict() for item in results]
    
    def get_items_by_palette_all(
        self,
        gender: Optional[Literal["women", "men"]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """取得所有色系的商品（用於每日推薦）"""
        result = {}
        for palette_key in PALETTE_KEYWORDS.keys():
            items = self.get_items(gender=gender, palette=palette_key, limit=4)
            if items:
                result[palette_key] = items
        return result


# 全域實例（快取）
_store_service: Optional[StoreItemService] = None


def get_store_service() -> StoreItemService:
    """取得店家服務實例（單例模式）"""
    global _store_service
    if _store_service is None:
        _store_service = StoreItemService()
    return _store_service
