"""
衣物 AI 分析結果的數據模型
"""
from pydantic import BaseModel
from typing import List, Optional


class AIClothingAnalysis(BaseModel):
    """
    Gemini AI 對衣物的分析結果
    """
    category: str = "special"  # 衣物類別
    colors: List[str] = []  # 顏色列表
    style: str = ""  # 風格
    material: str = ""  # 材質
    occasion: str = ""  # 場合
    size: str = ""  # 尺寸


class ClothingUploadResult(BaseModel):
    """
    衣物上傳和分析的完整結果
    """
    original_filename: str
    stored_path: str
    db_id: int
    category: str
    name: Optional[str] = None
    brand: Optional[str] = None
    style: Optional[str] = None
    cover_url: str
    bg_removed: bool = False
    ai_analysis: Optional[AIClothingAnalysis] = None


class UploadResponse(BaseModel):
    """
    上傳端點的響應
    """
    message: str
    results: List[ClothingUploadResult]
