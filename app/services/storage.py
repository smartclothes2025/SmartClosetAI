from google.cloud import storage
import os
import logging
from urllib.parse import urlparse
from fastapi import HTTPException
from datetime import timedelta # 🌟 引入 timedelta

logger = logging.getLogger("uvicorn.error")

def get_gcs_client() -> storage.Client:
    """初始化並回傳 GCS 客戶端，會自動使用 GOOGLE_APPLICATION_CREDENTIALS 憑證。"""
    try:
        return storage.Client()
    except Exception as e:
        logger.error(f"GCP 客戶端初始化失敗: {e}")
        raise ConnectionError("無法連接到 Google Cloud Storage，請檢查憑證設定。")


def upload_file_to_gcs_from_bytes(file_bytes: bytes, destination_blob_name: str, mime_type: str, bucket_name: str = None, public: bool = False) -> str:
    """
    將記憶體中的檔案內容 (bytes) 上傳到 GCS，並回傳 GCS URI (gs://...)。
    
    Args:
        file_bytes: 圖片的二進制內容。
        destination_blob_name: GCS 上的目標檔案路徑/名稱 (例如: category/filename_stamp.png)。
        mime_type: 檔案的 MIME 類型 (例如: image/png)。
        bucket_name: (可選) 覆寫環境變數中的 bucket 名稱。
        public: 是否設為公開存取 (建議 False，使用 GCS URI 存取 AI)。
        
    Returns:
        GCS URI (gs://[BUCKET_NAME]/[OBJECT_PATH])。
    """
    if bucket_name is None:
        bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCS bucket name not provided in args or environment.")
        
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    try:
        # 執行上傳
        blob.upload_from_string(
            file_bytes,
            content_type=mime_type 
        )
        
        # 設定公開存取權 (如果需要，但對於 AI 建議用 IAM/URI)
        if public:
            blob.make_public()
            
        # 回傳 GCS URI
        return f"gs://{bucket_name}/{destination_blob_name}"
        
    except Exception as e:
        logger.exception(f"上傳檔案到 GCS 失敗: {destination_blob_name}")
        raise HTTPException(status_code=500, detail=f"GCS 上傳失敗: {e}")


def upload_file_to_gcs(file_bytes: bytes, destination_blob_name: str, mime_type: str, bucket_name: str = None, public: bool = False) -> str:
    """
    Compatibility wrapper for older code that imports `upload_file_to_gcs`.
    Calls `upload_file_to_gcs_from_bytes` under the hood.
    """
    return upload_file_to_gcs_from_bytes(file_bytes, destination_blob_name, mime_type, bucket_name=bucket_name, public=public)


def delete_file_from_gcs(gcs_uri: str, bucket_name: str = None) -> bool:
    """
    從 GCS 刪除指定的物件，透過 GCS URI (gs://...) 識別。
    
    Args:
        gcs_uri: 完整的 GCS URI (例如: gs://bucket-name/path/to/file)。
    
    Returns:
        True 如果刪除成功，否則為 False。
    """
    if not gcs_uri.startswith("gs://"):
        logger.warning(f"提供的 URI 不是 GCS 格式: {gcs_uri}")
        return False
        
    try:
        # 解析 URI 獲取 bucket 名稱和物件路徑
        parsed = urlparse(gcs_uri)
        bucket_name_parsed = parsed.netloc
        object_name = parsed.path.lstrip('/')
        
        client = get_gcs_client()
        bucket = client.bucket(bucket_name_parsed)
        blob = bucket.blob(object_name)
        
        # 檢查物件是否存在後刪除
        if blob.exists():
            blob.delete()
            return True
        else:
            logger.warning(f"嘗試刪除 GCS 檔案，但檔案不存在: {gcs_uri}")
            return False
            
    except Exception as e:
        logger.exception(f"從 GCS 刪除檔案失敗: {gcs_uri}")
        return False


def generate_signed_url_from_gcs_uri(gcs_uri: str, expiration_minutes: int = 15) -> str:
    """
    🌟 核心功能：從 GCS URI 生成一個有時效性的 Signed URL，供前端存取非公開圖片。
    
    Args:
        gcs_uri: 完整的 GCS URI (例如: gs://bucket-name/path/to/file)。
        expiration_minutes: 網址的有效時間 (分鐘)。
        
    Returns:
        Signed URL (HTTPS 網址)。
    """
    if not gcs_uri.startswith("gs://"):
        return gcs_uri # 非 GCS 路徑直接返回

    try:
        parsed = urlparse(gcs_uri)
        bucket_name = parsed.netloc
        object_name = parsed.path.lstrip('/')
        
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        # 生成簽名網址 (使用 v4 簽名方式，需服務帳戶權限)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
        return signed_url
        
    except Exception as e:
        logger.error(f"生成 Signed URL 失敗 for {gcs_uri}: {e}")
        # 失敗時返回一個預設的錯誤圖片路徑，避免前端載入無限期掛起
        return "/error-image-placeholder.png"