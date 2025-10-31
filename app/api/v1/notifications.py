# app/api/v1/notifications.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timezone
import json
import uuid as _uuid
import logging

from app.core.db import get_db
from app.models.notification import Notification
from app.models.auth import User
from app.api.v1.posts import current_user_from_header
from pydantic import BaseModel

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["通知"])


# ===== Pydantic Models =====
class NotificationCreate(BaseModel):
    user_id: str
    type: str = "new_item"
    message: str
    details: Optional[str] = None
    payload: Optional[dict] = None  # 改為接收字典物件，不是字串


class NotificationUpdate(BaseModel):
    is_read: bool


# ===== API 端點 =====

@router.get("/")
async def get_notifications(
    user_id: str = Query(..., description="使用者 ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False, description="只顯示未讀通知"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """取得使用者的通知列表"""
    try:
        # 驗證使用者 ID (支援 Integer)
        try:
            user_int_id = int(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")
        
        # 確認請求者有權限查看通知（自己或管理員）
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權存取此使用者的通知")
        
        # 查詢通知
        query = db.query(Notification).filter(Notification.user_id == user_int_id)
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        total_count = query.count()
        unread_count = db.query(Notification).filter(
            Notification.user_id == user_int_id,
            Notification.is_read == False
        ).count()
        
        notifications = query.order_by(
            Notification.created_at.desc()
        ).offset(skip).limit(limit).all()
        
        # 轉換為前端期望的格式
        result = []
        for n in notifications:
            item = {
                "id": str(n.id),
                "user_id": n.user_id,
                "type": n.type,
                "message": n.message,
                "details": n.details,
                "payload": n.payload,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "read_at": n.read_at.isoformat() if n.read_at else None,
            }
            result.append(item)
        
        return {
            "notifications": result,
            "total": total_count,
            "unread_count": unread_count,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("取得通知失敗")
        raise HTTPException(status_code=500, detail=f"取得通知失敗: {str(e)}")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_notification(
    notification: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """建立新通知"""
    try:
        # 驗證使用者 ID (支援 Integer)
        try:
            user_int_id = int(notification.user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")
        
        # 檢查使用者是否存在
        user = db.query(User).filter(User.id == user_int_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="使用者不存在")
        
        # payload 直接使用（前端已經傳送字典物件）
        payload_dict = notification.payload
        
        # 建立通知
        new_notification = Notification(
            user_id=user_int_id,
            type=notification.type,
            message=notification.message,
            details=notification.details,
            payload=payload_dict,
            is_read=False,
        )
        
        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)
        
        return {
            "id": str(new_notification.id),
            "user_id": new_notification.user_id,
            "type": new_notification.type,
            "message": new_notification.message,
            "details": new_notification.details,
            "payload": new_notification.payload,
            "is_read": new_notification.is_read,
            "created_at": new_notification.created_at.isoformat() if new_notification.created_at else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("建立通知失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"建立通知失敗: {str(e)}")


@router.patch("/{notification_id}", status_code=status.HTTP_200_OK)
async def update_notification(
    notification_id: str,
    update_data: NotificationUpdate,
    user_id: str = Query(..., description="使用者 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """更新通知（標記已讀/未讀）"""
    try:
        # 驗證 UUID 和 user_id
        try:
            notif_uuid = _uuid.UUID(notification_id)
            user_int_id = int(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的 ID 格式")
        
        # 確認請求者有權限
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權修改此通知")
        
        # 查找通知
        notification = db.query(Notification).filter(
            Notification.id == notif_uuid,
            Notification.user_id == user_int_id
        ).first()
        
        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")
        
        # 更新狀態
        notification.is_read = update_data.is_read
        if update_data.is_read and not notification.read_at:
            notification.read_at = datetime.now(timezone.utc)
        elif not update_data.is_read:
            notification.read_at = None
        
        db.commit()
        db.refresh(notification)
        
        return {
            "id": str(notification.id),
            "is_read": notification.is_read,
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新通知失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新通知失敗: {str(e)}")


@router.post("/mark-all-read", status_code=status.HTTP_200_OK)
async def mark_all_read(
    user_id: str = Query(..., description="使用者 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """標記所有通知為已讀"""
    try:
        # 驗證使用者 ID
        try:
            user_int_id = int(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")
        
        # 確認請求者有權限
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權修改通知")
        
        # 批次更新
        now = datetime.now(timezone.utc)
        result = db.execute(
            text("""
                UPDATE notifications 
                SET is_read = true, read_at = :read_at
                WHERE user_id = :user_id AND is_read = false
            """),
            {"user_id": user_int_id, "read_at": now}
        )
        
        db.commit()
        
        return {
            "message": "所有通知已標記為已讀",
            "updated_count": result.rowcount
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("標記全部已讀失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"標記全部已讀失敗: {str(e)}")


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    user_id: str = Query(..., description="使用者 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """刪除單一通知"""
    try:
        # 驗證 UUID 和 user_id
        try:
            notif_uuid = _uuid.UUID(notification_id)
            user_int_id = int(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的 ID 格式")
        
        # 確認請求者有權限
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權刪除此通知")
        
        # 查找並刪除
        notification = db.query(Notification).filter(
            Notification.id == notif_uuid,
            Notification.user_id == user_int_id
        ).first()
        
        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")
        
        db.delete(notification)
        db.commit()
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("刪除通知失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除通知失敗: {str(e)}")


@router.delete("/", status_code=status.HTTP_200_OK)
async def delete_all_notifications(
    user_id: str = Query(..., description="使用者 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    """刪除使用者的所有通知"""
    try:
        # 驗證使用者 ID
        try:
            user_int_id = int(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")
        
        # 確認請求者有權限
        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權刪除通知")
        
        # 批次刪除
        result = db.execute(
            text("DELETE FROM notifications WHERE user_id = :user_id"),
            {"user_id": user_int_id}
        )
        
        db.commit()
        
        return {
            "message": "所有通知已刪除",
            "deleted_count": result.rowcount
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("刪除所有通知失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除所有通知失敗: {str(e)}")
