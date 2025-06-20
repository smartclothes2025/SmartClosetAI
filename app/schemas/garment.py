#schemas/garment.py
from pydantic import BaseModel

class Garment(BaseModel):
    garment_type: str
    color: str
    material: str
    style: str
#會用來接 Vision 回傳結果的「衣物模型」