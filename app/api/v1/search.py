# app/api/v1/search.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from typing import List, Dict, Any, Optional
import json
import logging

from app.core.db import get_db
from app.services.storage import generate_signed_url_from_gcs_uri

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["搜尋"])


def _https_from_gcs(gcs_uri: str) -> str:
    """將 GCS URI 轉換為簽名 HTTPS URL"""
    if not gcs_uri:
        return ""
    try:
        return generate_signed_url_from_gcs_uri(gcs_uri, expiration_minutes=60)
    except Exception as e:
        logger.warning(f"無法生成簽名 URL: {gcs_uri}, 錯誤: {e}")
        return ""


def _process_post_media(post_data: dict) -> dict:
    """
    統一處理貼文的媒體資料，將 GCS URI 轉換為可訪問的 HTTPS URL
    """
    # 處理 media 欄位（JSONB 陣列）
    try:
        media_raw = post_data.get("media")
        
        # 如果是字串，先解析為 JSON
        if isinstance(media_raw, str):
            media_parsed = json.loads(media_raw)
        elif isinstance(media_raw, list):
            media_parsed = media_raw
        else:
            media_parsed = []
        
        # 為每個媒體項目生成簽名 URL
        for m in media_parsed:
            if isinstance(m, dict):
                gcs_uri = m.get("gcs_uri", "")
                if gcs_uri and str(gcs_uri).startswith("gs://"):
                    signed_url = _https_from_gcs(gcs_uri)
                    if signed_url:
                        m["url"] = signed_url
                    else:
                        logger.warning(f"無法為 {gcs_uri} 生成簽名 URL")
                        m["url"] = ""
        
        post_data["media"] = media_parsed
        
        # 如果有媒體，設定封面圖片（取第一張）
        if media_parsed and len(media_parsed) > 0:
            first_media = media_parsed[0]
            if isinstance(first_media, dict):
                post_data["cover_image"] = first_media.get("url", "")
                post_data["thumbnail"] = first_media.get("url", "")
        else:
            post_data["cover_image"] = ""
            post_data["thumbnail"] = ""
            
    except Exception as e:
        logger.warning(f"處理貼文媒體資料時發生錯誤: {e}")
        post_data["media"] = []
        post_data["cover_image"] = ""
        post_data["thumbnail"] = ""
    
    return post_data


@router.get("/posts")
def search_posts(
    q: str = Query(..., min_length=1, description="搜尋關鍵字"),
    limit: int = Query(20, ge=1, le=100, description="回傳結果數量限制"),
    offset: int = Query(0, ge=0, description="分頁偏移量"),
    visibility: Optional[str] = Query(None, enum=["public", "friends", "private"], description="能見度篩選"),
    db: Session = Depends(get_db)
):
    """
    搜尋貼文標題或內容
    
    - **q**: 搜尋關鍵字（必填）
    - **limit**: 回傳結果數量（預設 20，最大 100）
    - **offset**: 分頁偏移量（預設 0）
    - **visibility**: 能見度篩選（可選：public, friends, private）
    
    搜尋範圍：
    - 貼文標題（title）
    - 貼文內容（content）
    - 標籤（tag）
    
    回傳結果會包含使用者資訊（display_name, email, avatar_url）
    """
    try:
        # 建立搜尋關鍵字（使用 PostgreSQL 的 ILIKE 進行不區分大小寫的模糊搜尋）
        search_pattern = f"%{q}%"
        
        # 基礎 SQL 查詢（使用 LEFT JOIN 獲取使用者資訊）
        base_query = """
            SELECT 
                p.*,
                u.display_name,
                u.email,
                u.avatar_url
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE (
                p.title ILIKE :search_pattern 
                OR p.content ILIKE :search_pattern
                OR p.tag ILIKE :search_pattern
            )
        """
        
        # 如果指定了 visibility，加入篩選條件
        if visibility:
            base_query += " AND p.visibility = :visibility"
        else:
            # 預設只搜尋公開貼文（避免隱私問題）
            base_query += " AND p.visibility = 'public'"
        
        # 加入排序和分頁
        base_query += """
            ORDER BY p.created_at DESC
            LIMIT :limit OFFSET :offset
        """
        
        # 準備參數
        params = {
            "search_pattern": search_pattern,
            "limit": limit,
            "offset": offset
        }
        
        if visibility:
            params["visibility"] = visibility
        
        # 執行查詢
        sql = text(base_query)
        rows = db.execute(sql, params).mappings().all()
        
        # 處理結果
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            # 使用統一的媒體處理函數
            item = _process_post_media(item)
            results.append(item)
        
        # 獲取總數（用於前端分頁）
        count_query = """
            SELECT COUNT(*) as total
            FROM user_post p
            WHERE (
                p.title ILIKE :search_pattern 
                OR p.content ILIKE :search_pattern
                OR p.tag ILIKE :search_pattern
            )
        """
        
        if visibility:
            count_query += " AND p.visibility = :visibility"
        else:
            count_query += " AND p.visibility = 'public'"
        
        count_params = {
            "search_pattern": search_pattern
        }
        if visibility:
            count_params["visibility"] = visibility
        
        total = db.execute(text(count_query), count_params).scalar()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": results,
            "query": q
        }
        
    except Exception as e:
        logger.exception("搜尋貼文時發生錯誤")
        raise HTTPException(status_code=500, detail=f"搜尋失敗: {str(e)}")


@router.get("/posts/by-tag")
def search_posts_by_tag(
    tag: str = Query(..., min_length=1, description="標籤名稱"),
    limit: int = Query(20, ge=1, le=100, description="回傳結果數量限制"),
    offset: int = Query(0, ge=0, description="分頁偏移量"),
    db: Session = Depends(get_db)
):
    """
    根據標籤搜尋貼文（精確匹配）
    
    - **tag**: 標籤名稱（必填）
    - **limit**: 回傳結果數量（預設 20，最大 100）
    - **offset**: 分頁偏移量（預設 0）
    
    只搜尋公開貼文
    """
    try:
        # 使用精確匹配搜尋標籤
        sql = text("""
            SELECT 
                p.*,
                u.display_name,
                u.email,
                u.avatar_url
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE p.tag = :tag 
            AND p.visibility = 'public'
            ORDER BY p.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        params = {
            "tag": tag,
            "limit": limit,
            "offset": offset
        }
        
        rows = db.execute(sql, params).mappings().all()
        
        # 處理結果
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            # 使用統一的媒體處理函數
            item = _process_post_media(item)
            results.append(item)
        
        # 獲取總數
        count_sql = text("""
            SELECT COUNT(*) as total
            FROM user_post
            WHERE tag = :tag AND visibility = 'public'
        """)
        total = db.execute(count_sql, {"tag": tag}).scalar()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": results,
            "tag": tag
        }
        
    except Exception as e:
        logger.exception("根據標籤搜尋貼文時發生錯誤")
        raise HTTPException(status_code=500, detail=f"搜尋失敗: {str(e)}")


@router.get("/posts/by-user")
def search_posts_by_user(
    user_id: str = Query(..., description="使用者 ID"),
    limit: int = Query(20, ge=1, le=100, description="回傳結果數量限制"),
    offset: int = Query(0, ge=0, description="分頁偏移量"),
    db: Session = Depends(get_db)
):
    """
    搜尋特定使用者的貼文
    
    - **user_id**: 使用者 ID（必填）
    - **limit**: 回傳結果數量（預設 20，最大 100）
    - **offset**: 分頁偏移量（預設 0）
    
    只搜尋公開貼文
    """
    try:
        sql = text("""
            SELECT 
                p.*,
                u.display_name,
                u.email,
                u.avatar_url
            FROM user_post p
            LEFT JOIN app_users u ON p.user_id = u.id
            WHERE p.user_id = :user_id 
            AND p.visibility = 'public'
            ORDER BY p.created_at DESC
            LIMIT :limit OFFSET :offset
        """)
        
        params = {
            "user_id": user_id,
            "limit": limit,
            "offset": offset
        }
        
        rows = db.execute(sql, params).mappings().all()
        
        # 處理結果
        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            # 使用統一的媒體處理函數
            item = _process_post_media(item)
            results.append(item)
        
        # 獲取總數
        count_sql = text("""
            SELECT COUNT(*) as total
            FROM user_post
            WHERE user_id = :user_id AND visibility = 'public'
        """)
        total = db.execute(count_sql, {"user_id": user_id}).scalar()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "results": results,
            "user_id": user_id
        }
        
    except Exception as e:
        logger.exception("搜尋使用者貼文時發生錯誤")
        raise HTTPException(status_code=500, detail=f"搜尋失敗: {str(e)}")


@router.get("/tags/popular")
def get_popular_tags(
    limit: int = Query(10, ge=1, le=50, description="回傳標籤數量"),
    db: Session = Depends(get_db)
):
    """
    獲取熱門標籤列表
    
    - **limit**: 回傳標籤數量（預設 10，最大 50）
    
    只統計公開貼文的標籤
    """
    try:
        sql = text("""
            SELECT 
                tag,
                COUNT(*) as count
            FROM user_post
            WHERE tag IS NOT NULL 
            AND tag != '' 
            AND visibility = 'public'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT :limit
        """)
        
        rows = db.execute(sql, {"limit": limit}).mappings().all()
        
        results = [
            {
                "tag": row["tag"],
                "count": row["count"]
            }
            for row in rows
        ]
        
        return {
            "total": len(results),
            "tags": results
        }
        
    except Exception as e:
        logger.exception("獲取熱門標籤時發生錯誤")
        raise HTTPException(status_code=500, detail=f"獲取熱門標籤失敗: {str(e)}")
