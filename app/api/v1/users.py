from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db import get_db

router = APIRouter()

@router.get("/users")
def list_clothes(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM public.users LIMIT :limit"), {"limit": limit}).mappings().all()
    return [dict(r) for r in rows]
