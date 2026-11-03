"""Admin-editable application settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..app_config import get_config, update_config
from ..db import get_db
from ..deps import get_admin_user
from ..models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/config")
def read_config(_: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return get_config(db)


@router.put("/config")
def write_config(body: dict, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    try:
        return update_config(db, body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
