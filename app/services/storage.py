# app/services/storage.py
# -*- coding: utf-8 -*-

import os
import re
import time
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote
from datetime import timedelta

from fastapi import HTTPException
from google.cloud import storage
from google.api_core.exceptions import NotFound, Forbidden, Conflict, TooManyRequests

logger = logging.getLogger("uvicorn.error")


# =====================================================================
# 基本：Client 取得
# =====================================================================
def get_gcs_client() -> storage.Client:
    """
    初始化並回傳 GCS 客戶端，會自動使用 GOOGLE_APPLICATION_CREDENTIALS 憑證。
    """
    try:
        return storage.Client()
    except Exception as e:
        logger.error(f"GCP 客戶端初始化失敗: {e}")
        raise ConnectionError("無法連接到 Google Cloud Storage，請檢查憑證設定。")


# =====================================================================
# 上傳：bytes -> GCS
# =====================================================================
def upload_file_to_gcs_from_bytes(
    file_bytes: bytes,
    destination_blob_name: str,
    mime_type: str,
    bucket_name: Optional[str] = None,
    public: bool = False,
) -> str:
    """
    將記憶體中的檔案內容 (bytes) 上傳到 GCS，並回傳 GCS URI (gs://...).

    Args:
        file_bytes: 檔案二進制內容。
        destination_blob_name: 目標路徑/檔名（例：clothes/tops/abc.png）。
        mime_type: MIME 類型（例：image/png）。
        bucket_name: 覆寫預設環境變數 GCS_BUCKET_NAME。
        public: True 會設定為公開（建議私有，前端以簽名網址取用）。

    Returns:
        str: GCS URI（gs://bucket/object）
    """
    if bucket_name is None:
        bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCS bucket name not provided in args or environment.")

    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    try:
        blob.upload_from_string(file_bytes, content_type=mime_type)
        if public:
            blob.make_public()
        return f"gs://{bucket_name}/{destination_blob_name}"
    except Exception as e:
        logger.exception(f"上傳檔案到 GCS 失敗: {destination_blob_name}")
        raise HTTPException(status_code=500, detail=f"GCS 上傳失敗: {e}")


def upload_file_to_gcs(
    file_bytes: bytes,
    destination_blob_name: str,
    mime_type: str,
    bucket_name: Optional[str] = None,
    public: bool = False,
) -> str:
    """
    與舊程式相容的包裝函式。實際呼叫 upload_file_to_gcs_from_bytes。
    """
    return upload_file_to_gcs_from_bytes(
        file_bytes,
        destination_blob_name,
        mime_type,
        bucket_name=bucket_name,
        public=public,
    )


# =====================================================================
# URL/URI 解析工具：把多種連結形式 => (bucket, blob)
# =====================================================================
_GCS_PUBLIC_1 = re.compile(r"^https?://storage\.googleapis\.com/(?P<bucket>[^/]+)/(?P<blob>.+)$")
_GCS_PUBLIC_2 = re.compile(r"^https?://(?P<bucket>[^./]+)\.storage\.googleapis\.com/(?P<blob>.+)$")
_GCS_CONSOLE  = re.compile(r"^https?://storage\.cloud\.google\.com/(?P<bucket>[^/]+)/(?P<blob>.+)$")
_FIREBASE_RE  = re.compile(r"^https?://firebasestorage\.googleapis\.com/v0/b/(?P<bucket>[^/]+)/o/(?P<blob_escaped>[^?]+)")
_GCS_PREFIXED = re.compile(r"^/?gcs/(?P<bucket>[^/]+)/(?P<blob>.+)$")            # gcs/<bucket>/<blob>
_BUCKET_BLOB  = re.compile(r"^(?P<bucket>[^/:]+?)/(?P<blob>[^/].+)$")           # bucket/blob（純相對）

def _parse_gcs_ref(uri_or_url: str) -> Optional[Tuple[str, str]]:
    """
    支援多種形式的 GCS 連結，回傳 (bucket, blob)；失敗回傳 None。
    - gs://bucket/path/to/file
    - https://storage.googleapis.com/bucket/path/to/file
    - https://bucket.storage.googleapis.com/path/to/file
    - https://storage.cloud.google.com/bucket/path/to/file
    - https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<urlencoded-blob>?...
    - 含 querystring 的簽名網址
    - gcs/<bucket>/<blob> 或 /gcs/<bucket>/<blob>
    - <bucket>/<blob>（純相對）
    """
    if not uri_or_url:
        return None

    s = uri_or_url.strip()

    # 1) gs://bucket/blob
    if s.startswith("gs://"):
        rest = s[5:]
        parts = rest.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None

    # 2) gcs/<bucket>/<blob> 或 /gcs/<bucket>/<blob>
    m = _GCS_PREFIXED.match(s)
    if m:
        return m.group("bucket"), m.group("blob")

    # 3) https://storage.googleapis.com/bucket/blob
    m = _GCS_PUBLIC_1.match(s)
    if m:
        return m.group("bucket"), m.group("blob")

    # 4) https://bucket.storage.googleapis.com/blob
    m = _GCS_PUBLIC_2.match(s)
    if m:
        return m.group("bucket"), m.group("blob")

    # 5) https://storage.cloud.google.com/bucket/blob
    m = _GCS_CONSOLE.match(s)
    if m:
        return m.group("bucket"), m.group("blob")

    # 6) Firebase 形式
    m = _FIREBASE_RE.match(s)
    if m:
        return m.group("bucket"), unquote(m.group("blob_escaped"))

    # 7) 一般簽名網址/其他情形
    try:
        p = urlparse(s)
        if p.netloc and p.path:
            if p.netloc.endswith(".storage.googleapis.com"):
                return p.netloc.split(".storage.googleapis.com")[0], p.path.lstrip("/")
            if p.netloc == "storage.googleapis.com":
                parts = p.path.lstrip("/").split("/", 1)
                if len(parts) == 2:
                    return parts[0], parts[1]
    except Exception:
        pass

    # 8) 純相對：<bucket>/<blob>
    m = _BUCKET_BLOB.match(s)
    if m:
        return m.group("bucket"), m.group("blob")

    return None


def is_gcs_like_url(uri_or_url: str) -> bool:
    """
    判斷是否「看起來」是 GCS（即使不是 gs://），用於路由側條件判斷。
    """
    if not uri_or_url:
        return False
    s = uri_or_url.strip()
    return (
        s.startswith("gs://")
        or "storage.googleapis.com" in s
        or "storage.cloud.google.com" in s
        or "firebasestorage.googleapis.com" in s
        or s.startswith("gcs/") or s.startswith("/gcs/")
    )


# =====================================================================
# 產生簽名網址
# =====================================================================
def generate_signed_url_from_gcs_uri(gcs_uri: str, expiration_minutes: int = 15) -> str:
    """
    從 GCS URI (gs://bucket/path) 生成 V4 簽名網址（HTTPS）給前端讀取非公開物件。
    失敗時回傳預設錯誤圖片，以避免前端掛住。

    Args:
        gcs_uri: 僅支援 gs:// 開頭；若非 gs:// 會原樣返回。
        expiration_minutes: 簽名網址有效分鐘數（預設 15 分鐘）。

    Returns:
        str: HTTPS 簽名網址；失敗則回 "/error-image-placeholder.png"
    """
    if not gcs_uri.startswith("gs://"):
        # 若 DB 裡存公開網址，這裡原樣返還即可
        return gcs_uri

    try:
        parsed = urlparse(gcs_uri)
        bucket_name = parsed.netloc
        object_name = parsed.path.lstrip("/")

        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
        return signed_url
    except Exception as e:
        logger.error(f"生成 Signed URL 失敗 for {gcs_uri}: {e}")
        return "/error-image-placeholder.png"


# =====================================================================
# 刪除物件：支援多種 URL/URI，冪等 + 重試
# =====================================================================
def delete_file_from_gcs(uri_or_url: str, bucket_name: Optional[str] = None) -> bool:
    """
    從 GCS 刪除指定物件。接受 gs://、storage.googleapis.com、storage.cloud.google.com、
    Firebase、gcs/<bucket>/... 等多種形式。
    - 回傳 True：刪除成功，或確認物件不存在（冪等）
    - 回傳 False：權限/連線/解析失敗等
    """
    parsed = _parse_gcs_ref(uri_or_url)
    if parsed:
        bkt, blob_path = parsed
    elif bucket_name:
        bkt, blob_path = bucket_name, uri_or_url.lstrip("/")
        logger.warning(f"無法解析 {uri_or_url}，改用 fallback bucket={bkt} blob={blob_path}")
    else:
        logger.warning(f"無法解析為 GCS 物件：{uri_or_url}")
        return False

    client = get_gcs_client()
    bucket = client.bucket(bkt)

    # 避免前/後導斜線、URL 編碼差異
    candidates = {blob_path, blob_path.lstrip("/")}
    try:
        decoded_once = unquote(blob_path)
        candidates.update({decoded_once, decoded_once.lstrip("/")})
    except Exception:
        pass

    # 重試策略：遇到 409/429/暫時性錯誤時 3 次退避
    def _delete_one(path: str) -> bool:
        blob = bucket.blob(path)
        try:
            blob.delete()
            logger.info(f"GCS 刪除成功：gs://{bkt}/{path}")
            return True
        except NotFound:
            logger.info(f"GCS 物件不存在（視為成功）：gs://{bkt}/{path}")
            return True
        except Forbidden as e:
            logger.error(f"GCS 刪除權限不足：gs://{bkt}/{path}；{e}")
            return False
        except (Conflict, TooManyRequests) as e:
            logger.warning(f"GCS 刪除需重試：gs://{bkt}/{path}；{e}")
            raise
        except Exception as e:
            logger.warning(f"GCS 刪除其他錯誤：gs://{bkt}/{path}；{e}")
            return False

    backoff = 0.4
    for attempt in range(3):
        for path in list(candidates):
            try:
                ok = _delete_one(path)
                if ok:
                    return True
            except (Conflict, TooManyRequests):
                time.sleep(backoff)
                backoff *= 2
                break
        else:
            break

    logger.warning(f"GCS 刪除失敗（所有嘗試皆未成功）：gs://{bkt}/{blob_path}")
    return False


