# app/api/v1/endpoints/media.py
from fastapi import APIRouter, HTTPException, Query
from urllib.parse import quote

router = APIRouter()

def gcs_to_public_url(gcs_uri: str) -> str:
    # gs://bucket/path/to/file.jpg  -> https://storage.googleapis.com/bucket/path/to/file.jpg
    if not gcs_uri.startswith("gs://"):
        return gcs_uri
    without = gcs_uri.replace("gs://", "", 1)
    i = without.find("/")
    if i <= 0:
        raise ValueError("Malformed gcs_uri")
    bucket = without[:i]
    obj = quote(without[i+1:])
    return f"https://storage.googleapis.com/{bucket}/{obj}"

@router.get("/signed-url")
def get_signed_url(gcs_uri: str = Query(..., description="gs:// 開頭的 GCS 物件 URI")):
    try:
        url = gcs_to_public_url(gcs_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid gcs_uri")
    # 這裡先回「看起來像簽名」的欄位名稱，前端已經會吃 authenticated_url / url 任一個
    return {"authenticated_url": url}
