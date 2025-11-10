# app/api/v1/ai_analyze.py
"""
AI 辨識衣物 API
提供獨立的 AI 辨識端點，讓前端在上傳前就能取得 AI 建議
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.auth import User
from app.api.v1.auth import get_current_user
from app.services.image_processing import gemini_classify_image, get_default_classification, process_image
import logging
from pathlib import Path
import uuid as _uuid
from typing import Optional
from fastapi.responses import FileResponse
import shutil
import os

router = APIRouter()


def cleanup_temp_file(file_path: str):
    """背景任務：清理臨時檔案"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logging.info(f"[清理] 已刪除臨時檔案: {file_path}")
    except Exception as e:
        logging.warning(f"[清理] 刪除臨時檔案失敗: {e}")


@router.post("/clothing")
async def analyze_clothing(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    使用 Gemini AI 辨識衣物圖片
    
    前端流程：
    1. 使用者在編輯頁選擇圖片
    2. 勾選「AI 辨識」後，呼叫此 API
    3. 取得 AI 建議的類別、顏色、材質等資訊
    4. 前端將建議填入表單（使用者可修改）
    5. 點擊「下一步」進入填寫頁面
    6. 最後點擊「完成」才真正上傳到資料庫
    
    回傳格式：
    {
        "success": true,
        "analysis": {
            "category": "tops",
            "colors": ["黑", "白"],
            "style": "簡約",
            "material": "棉",
            "occasion": "休閒",
            "size": "M"
        }
    }
    """
    
    # 驗證檔案類型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只接受圖片檔案")
    
    # 建立臨時目錄
    temp_dir = Path("temp_analysis")
    temp_dir.mkdir(exist_ok=True)
    
    # 生成臨時檔案名稱
    file_ext = Path(file.filename).suffix or ".jpg"
    temp_filename = f"ai_{_uuid.uuid4().hex}{file_ext}"
    temp_file_path = temp_dir / temp_filename
    
    try:
        # 儲存臨時檔案
        contents = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(contents)
        
        logging.info(f"[AI 辨識] 開始分析圖片: {temp_filename}")
        
        # 呼叫 Gemini AI 辨識
        try:
            analysis_result = gemini_classify_image(str(temp_file_path))
            
            # 轉換類別為中文（如果需要）
            category_map = {
                "tops": "上衣",
                "pants": "褲子",
                "skirts": "裙子",
                "dresses": "洋裝",
                "outerwear": "外套",
                "shoes": "鞋子",
                "bags": "包包",
                "hats": "帽子",
                "socks": "襪子",
                "jewelry": "配件",
                "special": "特殊",
                "bottoms": "下身",
                "pantsuits": "套裝"
            }
            
            # 保留英文類別，同時提供中文
            category_en = analysis_result.get("category", "tops")
            category_zh = category_map.get(category_en, "上衣")
            
            result = {
                "success": True,
                "analysis": {
                    "category": category_en,  # 英文類別（用於資料庫）
                    "category_zh": category_zh,  # 中文類別（用於顯示）
                    "colors": analysis_result.get("colors", []),
                    "style": analysis_result.get("style", ""),
                    "material": analysis_result.get("material", ""),
                    "occasion": analysis_result.get("occasion", ""),
                    "size": analysis_result.get("size", "")
                },
                "message": "AI 辨識成功"
            }
            
            logging.info(f"[AI 辨識] 分析完成: {result['analysis']}")
            return result
            
        except Exception as e:
            logging.error(f"[AI 辨識] Gemini 分析失敗: {e}", exc_info=True)
            # 回傳預設值，不中斷流程
            default_result = get_default_classification()
            return {
                "success": False,
                "analysis": default_result,
                "message": f"AI 辨識失敗，請手動填寫: {str(e)}"
            }
    
    finally:
        # 清理臨時檔案
        try:
            if temp_file_path.exists():
                temp_file_path.unlink()
                logging.info(f"[AI 辨識] 已刪除臨時檔案: {temp_filename}")
        except Exception as e:
            logging.warning(f"[AI 辨識] 刪除臨時檔案失敗: {e}")


@router.post("/clothing-batch")
async def analyze_clothing_batch(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批次辨識多張衣物圖片
    
    適用於使用者一次選擇多張圖片的情況
    """
    
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="一次最多只能辨識 10 張圖片")
    
    results = []
    
    for file in files:
        try:
            # 驗證檔案類型
            if not file.content_type or not file.content_type.startswith("image/"):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "message": "不是圖片檔案"
                })
                continue
            
            # 建立臨時目錄
            temp_dir = Path("temp_analysis")
            temp_dir.mkdir(exist_ok=True)
            
            # 生成臨時檔案名稱
            file_ext = Path(file.filename).suffix or ".jpg"
            temp_filename = f"ai_{_uuid.uuid4().hex}{file_ext}"
            temp_file_path = temp_dir / temp_filename
            
            try:
                # 儲存臨時檔案
                contents = await file.read()
                with open(temp_file_path, "wb") as f:
                    f.write(contents)
                
                # 呼叫 Gemini AI 辨識
                analysis_result = gemini_classify_image(str(temp_file_path))
                
                # 轉換類別
                category_map = {
                    "tops": "上衣",
                    "pants": "褲子",
                    "skirts": "裙子",
                    "dresses": "洋裝",
                    "outerwear": "外套",
                    "shoes": "鞋子",
                    "bags": "包包",
                    "hats": "帽子",
                    "socks": "襪子",
                    "jewelry": "配件",
                    "special": "特殊",
                    "bottoms": "下身",
                    "pantsuits": "套裝"
                }
                
                category_en = analysis_result.get("category", "tops")
                category_zh = category_map.get(category_en, "上衣")
                
                results.append({
                    "filename": file.filename,
                    "success": True,
                    "analysis": {
                        "category": category_en,
                        "category_zh": category_zh,
                        "colors": analysis_result.get("colors", []),
                        "style": analysis_result.get("style", ""),
                        "material": analysis_result.get("material", ""),
                        "occasion": analysis_result.get("occasion", ""),
                        "size": analysis_result.get("size", "")
                    }
                })
                
            finally:
                # 清理臨時檔案
                try:
                    if temp_file_path.exists():
                        temp_file_path.unlink()
                except Exception as e:
                    logging.warning(f"[AI 辨識] 刪除臨時檔案失敗: {e}")
        
        except Exception as e:
            logging.error(f"[AI 辨識] 處理 {file.filename} 失敗: {e}", exc_info=True)
            results.append({
                "filename": file.filename,
                "success": False,
                "message": str(e)
            })
    
    return {
        "success": True,
        "total": len(files),
        "results": results
    }


@router.post("/remove-background")
async def remove_background(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    去背 API - 移除圖片背景（僅用於預覽，不儲存到資料庫）
    
    前端流程：
    1. 使用者在編輯頁勾選「智慧去背」
    2. 點擊「下一步」時，呼叫此 API 處理每張圖片
    3. 取得去背後的圖片（PNG 格式，透明背景）
    4. 將去背後的圖片顯示在下一頁（僅預覽用）
    5. 回傳後自動刪除臨時檔案，不會永久儲存
    
    回傳：去背後的圖片檔案（PNG 格式）
    """
    
    # 驗證檔案類型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只接受圖片檔案")
    
    # 建立臨時目錄
    temp_dir = Path("temp_remove_bg")
    temp_dir.mkdir(exist_ok=True)
    
    # 生成臨時檔案名稱
    file_ext = Path(file.filename).suffix or ".jpg"
    temp_filename = f"rembg_{_uuid.uuid4().hex}{file_ext}"
    temp_file_path = temp_dir / temp_filename
    
    try:
        # 儲存臨時檔案
        contents = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(contents)
        
        logging.info(f"[去背] 開始處理圖片: {temp_filename}")
        
        # 呼叫去背處理
        try:
            result = process_image(str(temp_file_path))
            processed_path = Path(result["processed_image_path"])
            
            if not processed_path.exists():
                raise HTTPException(status_code=500, detail="去背處理失敗，找不到處理後的檔案")
            
            logging.info(f"[去背] 處理完成: {processed_path}")
            
            # 註冊背景任務：在回傳圖片後自動刪除處理後的檔案
            background_tasks.add_task(cleanup_temp_file, str(processed_path))
            
            # 回傳去背後的圖片（僅用於前端預覽，不會永久儲存）
            return FileResponse(
                path=str(processed_path),
                media_type="image/png",
                filename=f"removed_bg_{file.filename.rsplit('.', 1)[0]}.png"
            )
            
        except Exception as e:
            logging.error(f"[去背] 處理失敗: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"去背處理失敗: {str(e)}")
    
    finally:
        # 清理原始臨時檔案（處理後的檔案會在回傳後自動清理）
        try:
            if temp_file_path.exists():
                temp_file_path.unlink()
                logging.info(f"[去背] 已刪除原始臨時檔案: {temp_filename}")
        except Exception as e:
            logging.warning(f"[去背] 刪除臨時檔案失敗: {e}")
