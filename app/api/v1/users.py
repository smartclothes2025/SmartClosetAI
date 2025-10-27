from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
from app.core.db import get_db
from app.models.auth import User
import base64

router = APIRouter()


class BodyMetricsUpdate(BaseModel):
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    shoulder_cm: Optional[float] = None
    shoe_size: Optional[float] = None
    recorded_at: Optional[str] = None
    display_name: Optional[str] = None
    interformation: Optional[str] = None


def _update_app_user(db: Session, user_id, display_name: Optional[str], interformation: Optional[str]) -> Optional[str]:
    """Update app_users fields if provided; return effective display_name after update."""
    effective_display_name = None
    orm_user = db.query(User).filter(User.id == user_id).first()
    if not orm_user:
        return None
    if display_name is not None:
        orm_user.display_name = display_name
        effective_display_name = display_name
    if interformation is not None:
        orm_user.interformation = interformation
    db.flush()
    # If display_name not provided, fall back to current value
    return effective_display_name if effective_display_name is not None else getattr(orm_user, "display_name", None)


def _upsert_body_metrics(db: Session, params: dict):
    """Upsert into body_metrics using update-then-insert and return resulting row dict."""
    update_sql = text(
        """
    UPDATE body_metrics SET
        height_cm = COALESCE(:height_cm, height_cm),
        weight_kg = COALESCE(:weight_kg, weight_kg),
        chest_cm = COALESCE(:chest_cm, chest_cm),
        waist_cm = COALESCE(:waist_cm, waist_cm),
        hip_cm = COALESCE(:hip_cm, hip_cm),
        shoulder_cm = COALESCE(:shoulder_cm, shoulder_cm),
        shoe_size = COALESCE(:shoe_size, shoe_size),
        recorded_at = COALESCE(:recorded_at, recorded_at),
        display_name = COALESCE(:display_name, display_name)
    WHERE user_id = :user_id
    RETURNING *;
    """
    )

    insert_sql = text(
        """
    INSERT INTO body_metrics (user_id, height_cm, weight_kg, chest_cm, waist_cm, hip_cm, shoulder_cm, shoe_size, recorded_at, display_name)
    VALUES (:user_id, :height_cm, :weight_kg, :chest_cm, :waist_cm, :hip_cm, :shoulder_cm, :shoe_size, COALESCE(:recorded_at, now() at time zone 'utc'), :display_name)
    RETURNING *;
    """
    )

    res = db.execute(update_sql, params)
    row = res.mappings().first()
    if row:
        return dict(row)
    # no existing row -> insert
    res2 = db.execute(insert_sql, params)
    row2 = res2.mappings().first()
    return dict(row2) if row2 else {}


def _sanitize_mapping_values(obj: dict) -> dict:
    """Convert any bytes/bytearray values in a DB row mapping to base64 strings.
    This prevents FastAPI's encoder from trying to decode non-UTF8 bytes.
    """
    out = {}
    for k, v in obj.items():
        if isinstance(v, (bytes, bytearray)):
            try:
                out[k] = base64.b64encode(v).decode("ascii")
            except Exception:
                out[k] = None
        else:
            out[k] = v
    return out


def _get_user_from_auth_header(authorization: Optional[str], db: Session):
    """解析 Authorization header，接受簡單 token 格式: Bearer user-<id>-token"""
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    prefix = "user-"
    suffix = "-token"
    if not (isinstance(token, str) and token.startswith(prefix) and token.endswith(suffix)):
        return None
    user_id = token[len(prefix):-len(suffix)]
    try:
        # try integer id first
        uid = int(user_id)
    except Exception:
        uid = user_id
    row = db.execute(text("SELECT * FROM app_users WHERE id = :id"), {"id": uid}).mappings().first()
    return row


@router.get("/users")
def list_users(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM app_users LIMIT :limit"), {"limit": limit}).mappings().all()
    return [_sanitize_mapping_values(dict(r)) for r in rows]


@router.get("/me/body_metrics")
def get_my_body_metrics(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    user = _get_user_from_auth_header(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="需要授權")

    bm = db.execute(text("SELECT * FROM body_metrics WHERE user_id = :uid"), {"uid": user["id"]}).mappings().first()
    if not bm:
        # still return display_name for UI convenience
        return {"display_name": user.get("display_name") if isinstance(user, dict) else user["display_name"]}
    return _sanitize_mapping_values(dict(bm))


@router.put("/me/body_metrics")
def update_my_body_metrics(payload: BodyMetricsUpdate, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    user = _get_user_from_auth_header(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="需要授權")

    # Determine base display_name from current user row
    current_display_name = user.get("display_name") if isinstance(user, dict) else user["display_name"]

    # Update app_users first when needed and compute effective display_name
    try:
        if (payload.display_name is not None) or (payload.interformation is not None):
            updated_display = _update_app_user(
                db,
                user_id=user["id"],
                display_name=payload.display_name,
                interformation=payload.interformation,
            )
            if updated_display is not None:
                current_display_name = updated_display
    except Exception:
        db.rollback()

    params = {
        "user_id": user["id"],
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "chest_cm": payload.chest_cm,
        "waist_cm": payload.waist_cm,
        "hip_cm": payload.hip_cm,
        "shoulder_cm": payload.shoulder_cm,
        "shoe_size": payload.shoe_size,
        "recorded_at": payload.recorded_at,
        # use the app_users.display_name as the canonical display name (possibly updated above)
        "display_name": current_display_name,
    }

    try:
        result_row = _upsert_body_metrics(db, params)
        db.commit()
        return _sanitize_mapping_values(result_row)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新 body_metrics 失敗: {e}")