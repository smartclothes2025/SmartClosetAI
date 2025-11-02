from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import json
import uuid as _uuid
import logging

from app.core.db import get_db
from app.models.notification import Notification
from app.models.auth import User
from app.api.v1.posts import current_user_from_header  # 既有驗證
from pydantic import BaseModel

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["通知"])

# ===== Pydantic Models =====
class NotificationCreate(BaseModel):
    user_id: str
    type: str = "new_item"
    message: str
    details: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None

class NotificationUpdate(BaseModel):
    is_read: bool

# ===== 解析外部 user_id（數字 / UUID / 其他字串鍵）為內部整數主鍵 =====
def _resolve_user_int_id(user_id_raw: str, db: Session) -> int:
    if user_id_raw is None:
        raise HTTPException(status_code=400, detail="缺少使用者 ID")
    s = str(user_id_raw).strip()
    if not s:
        raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")

    # 1) 數字
    try:
        return int(s)
    except ValueError:
        pass

    # 2) UUID -> 以 User.uuid 對應回整數主鍵
    try:
        u = _uuid.UUID(s)
        user = db.query(User).filter(User.uuid == str(u)).first()
        if user:
            return int(user.id)
    except ValueError:
        pass

    # 3) （可選）其他字串鍵，如 username / email
    # user = db.query(User).filter(User.username == s).first()
    # if user:
    #     return int(user.id)

    raise HTTPException(status_code=400, detail="無效的使用者 ID 格式")

# ===== API 端點 =====
@router.get("/")
async def get_notifications(
    user_id: str = Query(..., description="使用者 ID（可為整數、UUID 或其他字串鍵）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False, description="只顯示未讀通知"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        user_int_id = _resolve_user_int_id(user_id, db)

        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權存取此使用者的通知")

        query = db.query(Notification).filter(Notification.user_id == user_int_id)
        if unread_only:
            query = query.filter(Notification.is_read == False)

        total_count = query.count()
        unread_count = db.query(Notification).filter(
            Notification.user_id == user_int_id,
            Notification.is_read == False
        ).count()

        notifications = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit).all()

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

        return {"notifications": result, "total": total_count, "unread_count": unread_count}
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
    try:
        user_int_id = _resolve_user_int_id(notification.user_id, db)

        user = db.query(User).filter(User.id == user_int_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="使用者不存在")

        payload_dict = notification.payload
        details_obj = notification.details

        # 去重：10 分鐘內相同 details.toast_id 視為重複
        toast_id = None
        if isinstance(details_obj, dict):
            toast_id = details_obj.get("toast_id")

        if toast_id:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                recent = db.query(Notification).filter(
                    Notification.user_id == user_int_id,
                    Notification.created_at >= cutoff
                ).all()
                for rn in recent:
                    rn_details = {}
                    try:
                        if rn.details is None:
                            rn_details = {}
                        elif isinstance(rn.details, dict):
                            rn_details = rn.details
                        else:
                            rn_details = json.loads(rn.details)
                    except Exception:
                        rn_details = {}
                    if rn_details and rn_details.get("toast_id") == toast_id:
                        existing = {
                            "id": str(rn.id),
                            "user_id": rn.user_id,
                            "type": rn.type,
                            "message": rn.message,
                            "details": rn.details,
                            "payload": rn.payload,
                            "is_read": rn.is_read,
                            "created_at": rn.created_at.isoformat() if rn.created_at else None,
                        }
                        return JSONResponse(content=existing, status_code=200)
            except Exception:
                logger.exception("去重檢查失敗，將繼續建立通知")

        new_notification = Notification(
            user_id=user_int_id,
            type=notification.type,
            message=notification.message,
            details=details_obj,
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
    user_id: str = Query(..., description="使用者 ID（可為整數、UUID 或其他字串鍵）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        try:
            notif_uuid = _uuid.UUID(notification_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的通知 ID 格式")

        user_int_id = _resolve_user_int_id(user_id, db)

        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權修改此通知")

        notification = db.query(Notification).filter(
            Notification.id == notif_uuid,
            Notification.user_id == user_int_id
        ).first()
        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")

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
    user_id: str = Query(..., description="使用者 ID（可為整數、UUID 或其他字串鍵）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        user_int_id = _resolve_user_int_id(user_id, db)

        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權修改通知")

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

        return {"message": "所有通知已標記為已讀", "updated_count": result.rowcount}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("標記全部已讀失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"標記全部已讀失敗: {str(e)}")

@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    user_id: str = Query(..., description="使用者 ID（可為整數、UUID 或其他字串鍵）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        try:
            notif_uuid = _uuid.UUID(notification_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="無效的通知 ID 格式")

        user_int_id = _resolve_user_int_id(user_id, db)

        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權刪除此通知")

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
    user_id: str = Query(..., description="使用者 ID（可為整數、UUID 或其他字串鍵）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(current_user_from_header),
):
    try:
        user_int_id = _resolve_user_int_id(user_id, db)

        is_admin = getattr(current_user, 'role', None) == 'admin'
        if current_user.id != user_int_id and not is_admin:
            raise HTTPException(status_code=403, detail="無權刪除通知")

        result = db.execute(text("DELETE FROM notifications WHERE user_id = :user_id"),
                            {"user_id": user_int_id})
        db.commit()

        return {"message": "所有通知已刪除", "deleted_count": result.rowcount}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("刪除所有通知失敗")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"刪除所有通知失敗: {str(e)}")
