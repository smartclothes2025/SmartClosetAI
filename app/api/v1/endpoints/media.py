# app/api/v1/endpoints/media.py
from fastapi import APIRouter, HTTPException, Query
from google.cloud import storage
from urllib.parse import quote
from datetime import timedelta
import os

router = APIRouter()

def parse_gcs(gcs_uri: str):
    if not gcs_uri.startswith("gs://"):
        raise ValueError("Invalid gcs_uri")
    s = gcs_uri.replace("gs://", "", 1)
    i = s.find("/")
    if i <= 0:
        raise ValueError("Invalid gcs_uri")
    return s[:i], s[i+1:]  # bucket, object

@router.get("/signed-url")
def get_signed_url(gcs_uri: str = Query(...)):
    try:
        bucket_name, object_name = parse_gcs(gcs_uri)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid gcs_uri")

    try:
        client = storage.Client()  # 需有預設認證或服務帳號 JSON
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=60),
            method="GET",
            # 如果 bucket 啟用 Requester Pays，需要加上：
            # additional_query_parameters={"userProject": os.environ.get("GOOGLE_CLOUD_PROJECT")}
        )
        return {"authenticated_url": url}
    except Exception as e:
        # 退回 public URL（若物件已公開可以用）
        public_url = f"https://storage.googleapis.com/{bucket_name}/{quote(object_name)}"
        return {"authenticated_url": public_url, "note": f"sign_failed:{e.__class__.__name__}"}
