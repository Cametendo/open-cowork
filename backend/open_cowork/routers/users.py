"""Admin user management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..app_config import ROLES
from ..db import get_db
from ..deps import get_admin_user
from ..models import User
from ..security import hash_password
from .auth import normalize_email

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str
    password: str = Field(min_length=8, max_length=256)
    role: str = "user"


class UpdateUserBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin").count()


@router.get("")
def list_users(_: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [u.public() for u in users]


@router.post("")
def create_user(body: CreateUserBody, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    email = normalize_email(body.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account with this email already exists")
    user = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return user.public()


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserBody,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
        if user.role == "admin" and body.role != "admin":
            if user.id == admin.id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't remove your own admin role")
            if _admin_count(db) <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one admin is required")
        user.role = body.role
    if body.name is not None:
        user.name = body.name.strip()
    if body.email is not None:
        email = normalize_email(body.email)
        clash = db.query(User).filter(User.email == email, User.id != user.id).first()
        if clash:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "An account with this email already exists")
        user.email = email
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    return user.public()


@router.delete("/{user_id}")
def delete_user(user_id: str, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't delete your own account")
    db.delete(user)
    db.commit()
    return {"ok": True}
