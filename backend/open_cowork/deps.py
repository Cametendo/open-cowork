from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import get_db, now
from .models import User
from .security import decode_token


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    user_id = decode_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    ts = now()
    if ts - (user.last_active_at or 0) > 60:
        user.last_active_at = ts
        db.commit()
    return user


def get_verified_user(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "user"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is pending activation by an admin")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
