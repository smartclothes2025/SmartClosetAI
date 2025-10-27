from pydantic import BaseModel
from typing import List

class WardrobeCreate(BaseModel):
    filename: str
    category: str
    color: str
    material: str
    style: str
    width: int
    height: int
    user_id: int

class WardrobeRead(WardrobeCreate):
    id: int

    class Config:
        orm_mode = True

class RGBColor(BaseModel):
    r: int
    g: int
    b: int

class ImageAnalysisResponse(BaseModel):
    dominant_colors: List[RGBColor]
    image_result_path: str
